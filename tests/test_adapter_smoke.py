"""Run generated adapter entry points with stub host APIs and a real local CLI."""
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import install
from test_ctx import git, run

ROOT=pathlib.Path(__file__).resolve().parents[1]


class GeneratedAdapterSmokeTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory();self.addCleanup(self.td.cleanup)
        self.repo=pathlib.Path(self.td.name).resolve()
        git(self.repo,'init','-q')
        run(['--cwd',str(self.repo),'init'])
        self.patch=mock.patch.object(install,'runtime_ctx',return_value=ROOT/'scripts/ctx.py')
        self.patch.start();self.addCleanup(self.patch.stop)

    def node_script(self, source, body):
        if not shutil.which('node'):
            self.skipTest('Node is not installed; generated Python/native adapters remain tested')
        adapter=self.repo/'adapter.mjs';adapter.write_text(source)
        script=self.repo/'smoke.mjs';script.write_text('import * as adapter from "./adapter.mjs";\nconst cwd='+json.dumps(str(self.repo))+';\n'+body)
        proc=subprocess.run(['node',str(script)],text=True,capture_output=True,timeout=30)
        self.assertEqual(proc.returncode,0,proc.stderr)
        return proc.stdout

    def test_pi_reinjects_after_compaction_in_both_profiles(self):
        for profile in ('startup-only','full'):
            source=install.templated_pi_extension(profile)
            self.assertIn('timeout:5000',source)
            self.node_script(source,'''
const hooks=new Map();adapter.default({on:(name,fn)=>hooks.set(name,fn)});
const c={cwd,sessionManager:{getSessionFile:()=>"pi-smoke-"+Date.now()}};
await hooks.get("session_start")({reason:"startup"},c);
const first=await hooks.get("before_agent_start")({},c);
if(!first?.message?.content) throw Error("Missing initial packet");
const duplicate=await hooks.get("before_agent_start")({},c);
if(duplicate) throw Error("Unexpected duplicate packet");
await hooks.get("session_compact")({},c);
const refreshed=await hooks.get("before_agent_start")({},c);
if(!refreshed?.message?.content) throw Error("Missing post-compaction packet");
''')

    def test_opencode_compaction_envelope(self):
        source=install.templated_opencode_plugin('startup-only')
        self.node_script(source,'''
const plugin=await adapter.ProjectContextPlugin({directory:cwd,worktree:cwd});
await plugin.event({event:{type:"session.created",properties:{sessionID:"oc-smoke"}}});
const output={context:[]};await plugin["experimental.session.compacting"]({sessionID:"oc-smoke"},output);
if(output.context.length!==1) throw Error("Missing compact context");
''')

    def test_hermes_first_turn_and_failure_fallback(self):
        files=install.templated_hermes_plugin_files('startup-only')
        # The generated source lives in the __init__.py entry, not its manifest.
        code=next(value for key,value in files.items() if key.endswith('.py'))
        namespace={'__name__':'hermes_smoke'};exec(compile(code,'hermes-adapter','exec'),namespace)
        namespace['on_start'](cwd=str(self.repo),session_id='hermes-smoke')
        first=namespace['pre_llm_call'](is_first_turn=True,cwd=str(self.repo),session_id='hermes-smoke')
        self.assertIn('context',first)
        self.assertIsNone(namespace['pre_llm_call'](is_first_turn=True,cwd=str(self.repo),session_id='hermes-smoke'))
        self.assertIn('timeout=5',code)

    def test_openclaw_bootstrap_file_in_writable_project(self):
        files=install.templated_openclaw_hook_files('startup-only')
        code=next(value for key,value in files.items() if key.endswith('.js'))
        self.node_script(code,'''
const event={type:"agent",action:"bootstrap",sessionKey:"claw-smoke",context:{workspaceDir:cwd,bootstrapFiles:[]}};
await adapter.default(event);
if(event.context.bootstrapFiles.length!==1) throw Error("Missing bootstrap file");
if(!event.context.bootstrapFiles[0].startsWith(cwd)) throw Error("Unexpected global cache dependency");
''')
