"""Delivery receipts are explicit acknowledgments, never draft side effects."""
import copy
import unittest

from repeat_resistant_briefs.briefs import select_result
from repeat_resistant_briefs.delivery import history_entries, record_delivery


def candidate(name='a', **extra):
    return dict(title=name, id=name, url=f'https://example.org/{name}?utm_source=x',
                quality=9, relevance=9, **extra)


def selection(rows=None, **kwargs):
    result = select_result(rows if rows is not None else [candidate(), candidate('b')], [],
                           as_of='2026-01-01', **kwargs).to_dict()
    return result


def receipt(items=None, **kwargs):
    return dict(report_id='report-1', delivered_at='2026-01-02',
                items=[{'identity': 'a'}] if items is None else items, **kwargs)


class DeliveryTests(unittest.TestCase):

    def collision(self):
        text = 'https://example.org/shared'
        rows = [dict(candidate('explicit'), id=text),
                dict(title='URL only', url=text, quality=9, relevance=9)]
        return text, rows, selection(rows)

    def test_colliding_typed_identities_record_separately_and_replay(self):
        text, rows, selected = self.collision()
        self.assertEqual([r['identity'] for r in selected['selected']], [text, text])
        for kinds in ([], ['id'], ['url'], ['id', 'url']):
            with self.subTest(kinds=kinds):
                ack = receipt([dict(identity=text, identity_type=kind) for kind in kinds])
                output = record_delivery(selected, [], ack)
                self.assertEqual(len(output['entries']), len(kinds))
                self.assertEqual({'id' if 'id' in r else 'url' for r in output['entries']}, set(kinds))
                self.assertTrue(all('identity_type' not in r for r in output['entries'] + output['receipts'][0]['items']))
                self.assertEqual(history_entries(output), output['entries'])
                self.assertEqual(record_delivery(selected, output, ack), output)
                next_run = select_result(rows, history_entries(output), as_of='2026-01-03')
                self.assertEqual({'id' if 'id' in r else 'url' for r in next_run.selected}, {'id', 'url'} - set(kinds))

    def test_colliding_untyped_receipt_requires_disambiguation(self):
        text, _, selected = self.collision()
        with self.assertRaisesRegex(ValueError, 'supply identity_type'):
            record_delivery(selected, [], receipt([dict(identity=text)]))

    def test_identity_type_is_optional_for_unique_exact_identity(self):
        for row in (candidate(), dict(title='URL', url='https://example.org/u', quality=9, relevance=9)):
            selected = selection([row])
            identity = selected['selected'][0]['identity']
            kind = 'id' if 'id' in row else 'url'
            untyped = receipt([dict(identity=identity)])
            typed = receipt([dict(identity=identity, identity_type=kind)])
            original = record_delivery(selected, [], untyped)
            self.assertEqual(record_delivery(selected, [], typed), original)
            self.assertEqual(record_delivery(selected, original, typed), original)
            with self.assertRaisesRegex(ValueError, 'not selected'):
                record_delivery(selected, [], receipt([dict(identity=identity, identity_type='url' if kind == 'id' else 'id')]))

    def test_unknown_or_malformed_identity_type_fails_clearly(self):
        for kind in ('ID', ' url', '', 'other', None, True, 1, [], {}):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'identity_type'):
                record_delivery(selection(), [], receipt([dict(identity='a', identity_type=kind)]))

    def test_duplicate_resolutions_include_mixed_typed_and_untyped(self):
        typed, untyped = dict(identity='a', identity_type='id'), dict(identity='a')
        for items in ([typed, untyped], [untyped, typed], [typed, typed]):
            with self.subTest(items=items), self.assertRaisesRegex(ValueError, 'duplicate receipt identity'):
                record_delivery(selection(), [], receipt(items))

    def test_duplicate_resolved_typed_history_is_rejected(self):
        output = record_delivery(selection(), [], receipt())
        output['entries'] *= 2
        output['receipts'][0]['items'] *= 2
        with self.assertRaisesRegex(ValueError, 'duplicate receipt identity'):
            history_entries(output)

    def test_receipt_identity_is_literal_not_an_alias(self):
        selected = selection([dict(candidate(), id=' a ')])
        output = record_delivery(selected, [], receipt([dict(identity=' a ', identity_type='id')]))
        self.assertEqual(output['entries'][0]['id'], ' a ')
        for identity in ('a', selected['selected'][0]['canonical_url']):
            with self.subTest(identity=identity), self.assertRaisesRegex(ValueError, 'not selected'):
                record_delivery(selected, [], receipt([dict(identity=identity)]))

    def test_only_explicitly_delivered_items_are_recorded(self):
        result = record_delivery(selection(), [], receipt())
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual([r['identity'] for r in result['entries']], ['a'])
        row = result['entries'][0]
        self.assertEqual(row['url'], 'https://example.org/a?utm_source=x')
        self.assertEqual(row['canonical_url'], 'https://example.org/a')
        self.assertEqual(row['id'], 'a')
        self.assertEqual(row['canonicalization_profile'], 'conservative')
        self.assertEqual(row['canonicalization_version'], 'conservative-v1')
        self.assertEqual(row['delivered_at'], '2026-01-02T00:00:00Z')
        self.assertEqual(row['report_id'], 'report-1')

    def test_url_identity_does_not_become_an_original_id(self):
        item = candidate(); del item['id']
        selected = selection([item])
        result = record_delivery(selected, [], receipt([{'identity': selected['selected'][0]['identity']}]))
        self.assertNotIn('id', result['entries'][0])

    def test_inputs_and_extracted_history_are_independent_copies(self):
        selected, history, ack = selection(), [dict(url='https://old.org')], receipt()
        before = copy.deepcopy((selected, history, ack))
        output = record_delivery(selected, history, ack)
        self.assertEqual((selected, history, ack), before)
        extracted = history_entries(output); extracted[0]['url'] = 'changed'
        self.assertNotEqual(extracted, output['entries'])
        self.assertEqual(history_entries(history), history)

    def test_empty_receipt_is_saved_and_idempotent(self):
        selected, ack = selection(), receipt([])
        output = record_delivery(selected, [], ack)
        self.assertEqual(output['entries'], [])
        self.assertEqual(len(output['receipts']), 1)
        self.assertEqual(record_delivery(selected, output, ack), output)
        with self.assertRaises(ValueError): record_delivery(selected, output, receipt())

    def test_normalized_replay_is_noop_but_conflicts_fail(self):
        selected = selection()
        ack = receipt([{'identity':'b'}, {'identity':'a'}])
        output = record_delivery(selected, [], ack)
        reordered = receipt([{'identity':'a'}, {'identity':'b'}])
        reordered['delivered_at'] = '2026-01-01T16:00:00-08:00'
        self.assertEqual(record_delivery(selected, output, reordered), output)
        for changed in [receipt([]), receipt(), dict(ack, delivered_at='2026-01-03')]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                record_delivery(selected, output, changed)
        changed_selection = selection([dict(candidate(), url='https://other.org/a'), candidate('b')])
        with self.assertRaises(ValueError): record_delivery(changed_selection, output, ack)

    def test_followup_requires_exact_event_and_preserves_evidence(self):
        follow = dict(event_id='release-2', what_changed='Released', why_it_matters='Available', evidence_url='https://evidence.org/v2')
        selected = selection([candidate(follow_up=follow)])
        for items in [[{'identity':'a'}], [{'identity':'a','event_id':'wrong'}]]:
            with self.assertRaises(ValueError): record_delivery(selected, [], receipt(items))
        ack = receipt([{'identity':'a','event_id':'release-2'}])
        output = record_delivery(selected, [], ack)
        self.assertEqual(output['entries'][0]['follow_up'], follow)
        self.assertEqual(output['entries'][0]['event_id'], 'release-2')
        changed = copy.deepcopy(selected)
        changed['selected'][0]['follow_up']['what_changed'] = 'Different evidence'
        with self.assertRaises(ValueError): record_delivery(changed, output, ack)
        with self.assertRaises(ValueError):
            record_delivery(selection(), [], receipt([{'identity':'a','event_id':'invented'}]))

    def test_resolved_receipt_requires_paired_event_evidence(self):
        follow = dict(event_id='release-2', what_changed='Released',
                      why_it_matters='Available', evidence_url='https://evidence.org/v2')
        selected = selection()
        good = record_delivery(selected, [], receipt())
        malformed = [dict(event_id='fake'), dict(follow_up=follow),
                     dict(event_id='wrong', follow_up=follow),
                     dict(event_id='release-2', follow_up={})]
        for evidence in malformed:
            history = copy.deepcopy(good)
            history['receipts'][0]['items'][0].update(evidence)
            history['entries'][0].update(evidence)
            before = copy.deepcopy(history)
            with self.subTest(evidence=evidence, operation='read'), self.assertRaises(ValueError):
                history_entries(history)
            with self.subTest(evidence=evidence, operation='record'), self.assertRaises(ValueError):
                record_delivery(selected, history, dict(receipt([]), report_id='report-2'))
            self.assertEqual(history, before)

    def test_structured_receipt_history_revalidates_and_replays(self):
        follow = dict(event_id='release-2', what_changed='Released',
                      why_it_matters='Available', evidence_url='https://evidence.org/v2')
        selected = selection([candidate(follow_up=follow)])
        ack = receipt([{'identity': 'a', 'event_id': 'release-2'}])
        history = record_delivery(selected, [], ack)
        self.assertEqual(history_entries(history), history['entries'])
        self.assertEqual(record_delivery(selected, history, ack), history)

    def test_legacy_bare_event_history_remains_accepted(self):
        legacy = [dict(url='https://old.org', event_id='legacy-event')]
        self.assertEqual(history_entries(legacy), legacy)
        selected, ack = selection(), receipt()
        history = record_delivery(selected, legacy, ack)
        self.assertEqual(history['entries'][0], legacy[0])
        self.assertEqual(history_entries(history), history['entries'])
        self.assertEqual(record_delivery(selected, history, ack), history)

    def test_malformed_receipts_fail(self):
        bad = [None, [], {}, dict(receipt(), report_id=' '), dict(receipt(), delivered_at=None),
               dict(receipt(), delivered_at='2026-01-02T00:00:00'), dict(receipt(), delivered_at='not-date'),
               dict(receipt(), items=None), dict(receipt(), items='a'), dict(receipt(), extra=True)]
        bad += [receipt(items) for items in [[None], ['a'], [{}], [{'identity':' '}],
                    [{'identity':'unknown'}], [{'identity':'a','event_id':''}],
                    [{'identity':'a','extra':1}], [{'identity':'a'},{'identity':'a'}]]]
        for ack in bad:
            with self.subTest(ack=ack), self.assertRaises(ValueError): record_delivery(selection(), [], ack)

    def test_timestamp_order_is_relative_to_selection_not_wall_clock(self):
        with self.assertRaises(ValueError):
            record_delivery(selection(), [], dict(receipt(), delivered_at='2025-12-31'))
        self.assertEqual(len(record_delivery(selection(), [], dict(receipt(), delivered_at='2999-01-01'))['entries']), 1)

    def test_malformed_selection_and_policy_fail(self):
        good = selection()
        bad = [None, {}, dict(good, schema_version=2), dict(good, schema_version=True),
               dict(good, selected={}), dict(good, policy={}), dict(good, policy=None)]
        for field, value in [('canonicalization_profile','unknown'), ('canonicalization_version','legacy-v1'),
                             ('strict','yes'), ('as_of','bad'), ('limit',True), ('min_quality',float('inf'))]:
            changed = copy.deepcopy(good); changed['policy'][field] = value; bad.append(changed)
        for field, value in [('identity','wrong'), ('canonical_url','https://wrong.org'),
                             ('url',None), ('id',''), ('follow_up',{}), ('canonicalization_version','legacy-v1')]:
            changed = copy.deepcopy(good); changed['selected'][0][field] = value; bad.append(changed)
        changed = copy.deepcopy(good); changed['selected'].append(changed['selected'][0]); bad.append(changed)
        changed = copy.deepcopy(good); del changed['schema_version']; bad.append(changed)
        for selected in bad:
            with self.subTest(selected=selected), self.assertRaises(ValueError): record_delivery(selected, [], receipt([]))

    def test_malformed_history_fails_even_when_receipt_empty(self):
        good = record_delivery(selection(), [], receipt())
        bad = [None, {}, {'schema_version':1,'entries':[]}, dict(good, schema_version=2),
               dict(good, schema_version=True), dict(good, entries={}), dict(good, receipts={}),
               dict(good, receipts=[{}]), dict(good, receipts=good['receipts']*2),
               [{'url':'https://old.org', 'delivered_at':'invalid'}],
               [{'url':'https://old.org', 'date':'2026-01-01', 'delivered_at':'2026-01-02'}]]
        for hist in bad:
            with self.subTest(history=hist), self.assertRaises(ValueError): history_entries(hist)
            with self.subTest(history=hist), self.assertRaises(ValueError): record_delivery(selection(), hist, receipt([]))

    def test_conflicting_history_provenance_is_not_reinterpreted(self):
        output = record_delivery(selection(), [], receipt())
        legacy = selection(profile='legacy')
        with self.assertRaises(ValueError): record_delivery(legacy, output, dict(receipt([]), report_id='r2'))
        for field, value in [('canonicalization_version','legacy-v1'), ('canonical_url','https://wrong.org'), ('identity','wrong')]:
            bad = copy.deepcopy(output); bad['entries'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): history_entries(bad)

    def test_envelope_receipts_must_correspond_to_delivered_entries(self):
        good = record_delivery(selection(), [], receipt())
        missing = copy.deepcopy(good); missing['entries'] = []
        duplicate = copy.deepcopy(good); duplicate['entries'] *= 2
        altered = copy.deepcopy(good); altered['entries'][0]['delivered_at'] = '2026-01-03'
        malformed = copy.deepcopy(good); malformed['receipts'][0]['items'][0]['identity'] = 'wrong'
        for bad in (missing, duplicate, altered, malformed):
            with self.subTest(history=bad), self.assertRaises(ValueError): history_entries(bad)

    def test_orphan_report_entry_requires_a_recorded_receipt(self):
        history = {'schema_version': 1, 'entries': [dict(
            url='https://old.org', report_id='orphan', delivered_at='2026-01-02')],
            'receipts': []}
        with self.assertRaisesRegex(ValueError, 'report_id.*receipt'):
            history_entries(history)

    def test_stripped_receipts_cannot_be_replayed_into_duplicate_entries(self):
        selected, ack = selection(), receipt()
        history = record_delivery(selected, [], ack)
        history['receipts'] = []
        before = copy.deepcopy(history)
        with self.subTest(operation='read'), self.assertRaises(ValueError):
            history_entries(history)
        for replay in (ack, receipt([])):
            with self.subTest(receipt=replay), self.assertRaises(ValueError):
                record_delivery(selected, history, replay)
        self.assertEqual(history, before)

    def test_known_report_with_mismatching_entry_is_rejected(self):
        selected, ack = selection(), receipt()
        history = record_delivery(selected, [], ack)
        history['entries'][0]['delivered_at'] = '2026-01-03'
        with self.assertRaises(ValueError): history_entries(history)
        with self.assertRaises(ValueError): record_delivery(selected, history, ack)

    def test_orphan_is_rejected_even_alongside_a_valid_recorded_report(self):
        history = record_delivery(selection(), [], receipt())
        history['entries'].append(dict(history['entries'][0], report_id='orphan'))
        with self.assertRaises(ValueError): history_entries(history)

    def test_entry_report_id_must_be_a_nonblank_string(self):
        for report_id in (None, True, 1, [], {}, '', ' \t'):
            history = {'schema_version': 1, 'entries': [dict(
                url='https://old.org', report_id=report_id)], 'receipts': []}
            with self.subTest(report_id=report_id), self.assertRaisesRegex(ValueError, 'report_id'):
                history_entries(history)
            with self.subTest(report_id=report_id), self.assertRaises(ValueError):
                record_delivery(selection(), history, receipt([]))

    def test_legacy_report_tagged_rows_require_explicit_migration(self):
        recorded = record_delivery(selection(), [], receipt())
        for history in (recorded['entries'], [dict(url='https://old.org', report_id=None)]):
            with self.subTest(history=history), self.assertRaisesRegex(ValueError, 'legacy.*migrat'):
                history_entries(history)
            with self.subTest(history=history), self.assertRaisesRegex(ValueError, 'legacy.*migrat'):
                record_delivery(selection(), history, receipt())

    def test_output_and_replays_revalidate_for_normal_and_empty_receipts(self):
        for items in ([{'identity': 'a'}], []):
            with self.subTest(items=items):
                selected, ack = selection(), receipt(items)
                output = record_delivery(selected, [dict(url='https://old.org')], ack)
                self.assertEqual(history_entries(output), output['entries'])
                replay = record_delivery(selected, output, ack)
                self.assertEqual(replay, output)
                self.assertEqual(history_entries(replay), replay['entries'])
                self.assertEqual(len(replay['receipts']), 1)
                self.assertEqual(len(replay['entries']), 1 + len(items))

    def test_policy_semantics_and_provenance_are_validated(self):
        for field, value in [('weights', {'quality': 1, 'relevance': 0}),
                             ('identity_matching', 'transitive'), ('deduplication', 'all_rows')]:
            bad = selection(); bad['policy'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): record_delivery(bad, [], receipt([]))
        bad = selection(); bad['selected'][0]['schema_version'] = 99
        with self.assertRaises(ValueError): record_delivery(bad, [], receipt([]))

    def test_nonstructured_event_id_does_not_become_delivery_evidence(self):
        selected = selection([candidate(event_id='unsupported')])
        output = record_delivery(selected, [], receipt())
        self.assertNotIn('event_id', output['entries'][0])

    def test_strict_multiple_runs_only_suppress_delivered_sources_and_events(self):
        candidates = [candidate(), candidate('b')]
        output = record_delivery(selection(candidates), [], receipt())
        next_run = select_result(candidates, history_entries(output), as_of='2026-01-03').to_dict()
        self.assertEqual([r['identity'] for r in next_run['selected']], ['b'])
        follow = dict(event_id='e2', what_changed='new release', why_it_matters='new feature', evidence_url='https://evidence.org')
        next_run = select_result([candidate(follow_up=follow)], history_entries(output), as_of='2026-01-03').to_dict()

        ack = dict(receipt([{'identity':'a','event_id':'e2'}]), report_id='report-2', delivered_at='2026-01-03')
        output = record_delivery(next_run, output, ack)
        final = select_result([candidate(follow_up=follow)], history_entries(output), as_of='2026-01-04')
        self.assertEqual(final.selected, [])


if __name__ == '__main__': unittest.main()
