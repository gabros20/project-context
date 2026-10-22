"""Fixed-budget retrieval and persistence regressions from the agent usability review."""
import argparse
import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from scripts import ctx
from test_ctx import git, run


def record(eid, scopes, kind='observation', **fields):
    return {'entry_id': eid, 'timestamp': '2026-10-22T10:00:00Z', 'record_type': kind,
            'scope': scopes, 'context': eid, 'importance': 'high', **fields}


class RetrievalTests(unittest.TestCase):
    def test_narrow_reflection_never_hides_unrelated_history(self):
        auth = record('auth', ['auth'])
        docs = record('docs', ['docs'])
        ref = record('ref', ['docs'], 'reflection', coverage={'scope':['docs'], 'through_entry_id':'docs', 'supporting_entry_ids':['docs']})
        selected, reflection = ctx.select_context_entries([auth, docs, ref], None, None, 6)
        self.assertEqual(reflection['entry_id'], 'ref')
        self.assertIn('auth', [x['entry_id'] for x in selected])
        payload = {'scope': [], 'coverage': {}}
        ctx.reflection_coverage([auth, docs, ref], payload)
        self.assertEqual(payload['coverage']['supporting_entry_ids'], ['auth'])

    def test_mixed_scope_coverage_is_conservative(self):
        source = record('source', ['auth', 'api'])
        ref = record('ref', ['auth'], 'reflection', coverage={'scope':['auth'], 'supporting_entry_ids':['source']})
        self.assertEqual(ctx.covered_entry_ids([source, ref]), set())
        self.assertEqual(ctx.covered_entry_ids([source, ref], ['auth']), {'source'})
        self.assertEqual(ctx.covered_entry_ids([source, ref], ['api']), set())

    def test_multiple_reflections_remain_available_globally(self):
        a=record('a',['auth']); d=record('d',['docs'])
        ar=record('ar',['auth'],'reflection',coverage={'scope':['auth'],'supporting_entry_ids':['a']})
        dr=record('dr',['docs'],'reflection',coverage={'scope':['docs'],'supporting_entry_ids':['d']})
        selected, ref=ctx.select_context_entries([a,d,ar,dr],None,None,6)
        self.assertEqual({e['entry_id'] for e in selected}, {'ar'})
        self.assertEqual(ref['entry_id'],'dr')

    def test_legacy_watermark_does_not_discard_unproven_sources(self):
        source=record('a',['auth'])
        ref=record('r',[],'reflection',coverage={'through_entry_id':'a'})
        self.assertEqual(ctx.covered_entry_ids([source,ref]),set())

    def test_explicit_empty_reflection_never_expands_to_all_sources(self):
        with self.assertRaises(ctx.ContextError):
            ctx.reflection_coverage([record('a',['auth'])], {'scope':[], 'coverage':{'supporting_entry_ids':[]}})

    def test_budget_keeps_handoff_actions_and_blocker(self):
        handoff=record('handoff',['core'],'handoff',context='Long historical background. '*400,
                       current_state={'status':'in_progress','blockers':['BLOCKER_X'],'next_steps':['NEXT_ACTION_X']})
        packet=ctx.pack_context_packet('HEADER',None,[handoff],300,None,False)
        self.assertIn('NEXT_ACTION_X',packet)
        self.assertIn('BLOCKER_X',packet)
        self.assertIn('ctx show handoff',packet)
        self.assertLessEqual(len(packet),1200)

    def test_budget_keeps_reflected_constraint(self):
        ref=record('r',['core'],'reflection',context='Old background. '*400,durable_state={'constraints':['KEEP_60PX']})
        packet=ctx.pack_context_packet('HEADER',ref,[],300,None,False)
        self.assertIn('KEEP_60PX',packet)

    def test_extractor_budget_prefers_newest(self):
        self.assertIn('NEW_ACTION',ctx.blocks_with_budget(['old '*300,'NEW_ACTION'],100))

    def test_partial_resolution_preserves_sibling_issue(self):
        source=record('source',['core'],current_state={'blockers':['done','still blocked'],'next_steps':['next']})
        fix=record('fix',['core'],related_entries={'resolves':['source#/current_state/blockers/0']})
        state=ctx.active_entries([source,fix])[0]['current_state']
        self.assertEqual(state['blockers'],['still blocked'])
        self.assertEqual(state['next_steps'],['next'])

    def test_supersession_and_whole_state_resolution(self):
        old=record('old',['core'],current_state={'blockers':['old block']})
        replacement=record('new',['core'],related_entries={'supersedes':['old']})
        self.assertEqual([e['entry_id'] for e in ctx.active_entries([old,replacement])],['new'])
        fix=record('fix',['core'],related_entries={'resolves':['old']})
        self.assertNotIn('current_state',ctx.active_entries([old,fix])[0])
        self.assertIn('current_state',old)  # projection never mutates history

    def test_unknown_resolution_sources_and_pointers_rejected(self):
        with self.assertRaises(ctx.ContextError):
            ctx.validate_relations({'related_entries':{'resolves':['missing']}},[])
        with self.assertRaises(ctx.ContextError):
            ctx.validate_relations({'related_entries':{'resolves':['a#/context']}},[record('a',['core'])])

    def test_schema_runtime_parity_and_indexed_diagnostics(self):
        payload={'record_type':'observation','scope':['core'],'context':'x','verification':[{'check':'tests','outcome':'21 passed'}], 'current_state':{'blockers':'wrong'}}
        errors=ctx.validate_semantic(payload)
        self.assertTrue(any('/verification/0/outcome: enum' in e for e in errors))
        self.assertTrue(any('/current_state/blockers: type' in e for e in errors))
        self.assertIn('details',ctx.entry_schema()['properties']['verification']['items']['properties'])

    def test_templates_validate_without_authoring_metadata(self):
        for kind in ctx.RECORD_TYPES:
            self.assertEqual(ctx.validate_semantic(ctx.template_payload(kind)),[])
            self.assertNotIn('agent',ctx.template_payload(kind))

    def test_fixed_budget_search_corpus(self):
        corpus=[record('safari',['home-new'],context='Safari mobile viewport requires hero height plus 60px.'),
                record('auth',['sessions'],context='Concurrent refresh rotation requires a previous-token grace period.'),
                record('video',['render'],context='Keep the final decoded video frame instead of swapping a poster.'),
                record('tokens',['design'],context='Use semantic color tokens in the stylesheet.'),
                record('deploy',['delivery'],context='Vercel deployment alias can lag a GitHub push.')]
        cases={'Safari viewport hero':'safari','concurrent refresh grace':'auth','decoded frame poster':'video','semantic color stylesheet':'tokens','Vercel alias push':'deploy'}
        for query, expected in cases.items():
            self.assertEqual(ctx.ranked_entries(corpus,query)[0][1]['entry_id'],expected)
            self.assertLessEqual(len(ctx.search_packet(corpus,query,300)),1200)
        self.assertIn('No matching memory',ctx.search_packet(corpus,'unfindableXYZ',300))

    def test_multi_path_and_zero_match_discovery(self):
        source=record('a',['homepage'],related_paths=['src/hero.ts'])
        self.assertTrue(ctx.matches_path(source,['src/missing.ts','src/hero.ts']))
        self.assertIn('homepage',ctx.no_match_message([source],['home']))


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)
        self.repo=pathlib.Path(self.td.name)
        git(self.repo,'init','-q');git(self.repo,'config','user.name','Test');git(self.repo,'config','user.email','test@example.com')
        (self.repo/'README.md').write_text('hello\n');git(self.repo,'add','README.md');git(self.repo,'commit','-qm','init')
        run(['--cwd',str(self.repo),'init'])

    def cli(self,*args,payload=None,check=True):
        return run(['--cwd',str(self.repo),*args],input_text=json.dumps(payload) if payload is not None else None,check=check)

    def append(self, **fields):
        payload={'record_type':'observation','scope':['core'],'context':'A useful durable constraint.',**fields}
        return json.loads(self.cli('append','--agent','codex','--input','-',payload=payload).stdout)

    def test_search_show_scopes_schema_commands(self):
        info=self.append(context='Safari browser viewport constraint')
        self.assertIn(info['entry_id'],self.cli('search','Safari').stdout)
        self.assertIn('core',self.cli('scopes').stdout)
        self.assertIn('Safari',self.cli('show',info['entry_id'],'--section','context').stdout)
        self.assertIn('details',self.cli('schema','--section','verification').stdout)
        self.assertIn('verification',self.cli('template','observation','--minimal').stdout)
        self.assertIn('Safari',self.cli('context','--query','Safari').stdout)
        self.assertIn('No matching memory',self.cli('context','--scope','wrong').stdout)

    def test_idempotent_concurrent_retry_key(self):
        payload={'record_type':'observation','scope':['core'],'context':'Retry-safe checkpoint'}
        first=self.cli('append','--input','-','--idempotency-key','task-1',payload=payload)
        second=self.cli('append','--input','-','--idempotency-key','task-1',payload=payload)
        self.assertEqual(json.loads(first.stdout)['entry_id'],json.loads(second.stdout)['entry_id'])
        self.assertEqual(len((self.repo/'.agent/PROJECT_CONTEXT.jsonl').read_text().splitlines()),1)

    def test_idempotency_conflict_and_json_errors(self):
        payload={'record_type':'observation','scope':['core'],'context':'Original payload'}
        self.cli('append','--input','-','--idempotency-key','conflict-key',payload=payload)
        changed={**payload,'context':'Different payload'}
        result=self.cli('append','--input','-','--idempotency-key','conflict-key',payload=changed,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('different semantic payload',result.stderr)
        invalid={**payload,'verification':[{'check':'tests','outcome':'21 passed'}]}
        result=self.cli('append','--json-errors','--input','-',payload=invalid,check=False)
        self.assertEqual(json.loads(result.stderr)['diagnostics'][0]['pointer'],'/verification/0/outcome')

    def test_concurrent_duplicate_retry(self):
        import concurrent.futures
        payload={'record_type':'observation','scope':['core'],'context':'Two simultaneous retries'}
        def call(_):
            return json.loads(self.cli('append','--input','-','--idempotency-key','concurrent',payload=payload).stdout)['entry_id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(call,range(2)))
        self.assertEqual(ids[0],ids[1])
        self.assertEqual(len((self.repo/'.agent/PROJECT_CONTEXT.jsonl').read_text().splitlines()),1)

    def test_post_append_runtime_failure_reports_success(self):
        args=ctx.build_parser().parse_args(['--cwd',str(self.repo),'append','--input','-','--agent','codex','--session-id','explicit'])
        payload={'record_type':'observation','scope':['core'],'context':'Persist despite ancillary state failure.'}
        output=io.StringIO();err=io.StringIO()
        with mock.patch.object(ctx,'read_payload',return_value=payload),mock.patch.object(ctx,'update_runtime_after_checkpoint',side_effect=PermissionError('read-only runtime')),contextlib.redirect_stdout(output),contextlib.redirect_stderr(err):
            self.assertEqual(ctx.cmd_append(args),0)
        self.assertIn('entry_id',json.loads(output.getvalue()))
        self.assertIn('persisted',err.getvalue())
        self.assertEqual(len((self.repo/'.agent/PROJECT_CONTEXT.jsonl').read_text().splitlines()),1)

    def test_check_only_does_not_create_runtime(self):
        self.cli('append','--check','--input','-',payload={'record_type':'observation','scope':['core'],'context':'Check only'})
        self.assertFalse((self.repo/'.agent/runtime').exists())
        self.assertEqual((self.repo/'.agent/PROJECT_CONTEXT.jsonl').read_text(),'')

    def test_sandbox_runtime_does_not_require_home_cache(self):
        with mock.patch.dict(os.environ,{'XDG_CACHE_HOME':'/not/a/writable/cache'}):
            path=ctx.runtime_dir(self.repo)
            self.assertTrue(path.is_relative_to(self.repo.resolve()))
            self.assertTrue(ctx.lock_path_for(self.repo/'.agent/PROJECT_CONTEXT.jsonl').is_relative_to(self.repo.resolve()))

    def test_ambiguous_same_host_sessions_do_not_cross_attribute(self):
        for sid in ('one','two'):
            ctx.write_json_atomic(ctx.session_state_path(self.repo,sid),{'host':'codex','session_id':sid})
        with mock.patch.dict(os.environ,{'PROJECT_CONTEXT_SESSION_ID':''}),contextlib.redirect_stderr(io.StringIO()):
            self.assertTrue(ctx.resolve_session_id(self.repo,'codex',None).startswith('manual-'))
        self.assertEqual(ctx.resolve_session_id(self.repo,'codex','one'),'one')

    def test_emission_deduplication_and_compaction_refresh(self):
        cfg=ctx.load_config(self.repo)
        first=ctx.startup_delivery(self.repo,cfg,'codex','one')
        self.assertTrue(first)
        self.assertEqual(ctx.startup_delivery(self.repo,cfg,'codex','one'),'')
        self.assertTrue(ctx.startup_delivery(self.repo,cfg,'codex','one',compact=True))
        self.assertTrue(ctx.startup_delivery(self.repo,cfg,'codex','two'))
        self.assertNotIn('runtime',ctx.filtered_git_status(self.repo))

    def test_doctor_does_not_pretend_to_test_host_consumption(self):
        self.append()
        health=json.loads(self.cli('doctor','--host','codex','--json','--self-test').stdout)
        self.assertEqual(health['self_test'],'passed')
        self.assertTrue(health['runtime_writable'])
        self.assertIn('check user installation',health['diagnosis'])

    def test_prepare_is_bounded_and_does_not_append(self):
        self.append();before=(self.repo/'.agent/PROJECT_CONTEXT.jsonl').read_text()
        result=self.cli('reflect','--prepare','--scope','core','--budget','700').stdout
        self.assertIn('supporting_entry_ids',result)
        self.assertIn('uncovered=1',result)
        self.assertLessEqual(len(result),2801)
        self.assertEqual(before,(self.repo/'.agent/PROJECT_CONTEXT.jsonl').read_text())

    def test_open_current_and_history(self):
        source=self.append(current_state={'blockers':['OLD_BLOCKER']})
        self.append(related_entries={'resolves':[source['entry_id']]})
        self.assertNotIn('OLD_BLOCKER',self.cli('blockers').stdout)
        self.assertIn('OLD_BLOCKER',self.cli('blockers','--history').stdout)


if __name__=='__main__':
    unittest.main()
