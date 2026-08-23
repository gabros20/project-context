import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
INSTALL = ROOT / "scripts" / "install.py"
HOSTS = ["claude","codex","grok","opencode","cursor","droid","pi","antigravity","hermes","openclaw"]


def git(repo, *args):
    p=subprocess.run(["git","-C",str(repo),*args],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise AssertionError(p.stderr)


def run_install(args, home, cwd=None, check=True):
    env=os.environ.copy(); env["HOME"]=str(home)
    p=subprocess.run([sys.executable,str(INSTALL),*args],cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if check and p.returncode:
        raise AssertionError(f"install failed\nstdout={p.stdout}\nstderr={p.stderr}")
    return p


class UniversalInstallTests(unittest.TestCase):
    def repo(self, td):
        r=pathlib.Path(td)/"repo"; r.mkdir(); git(r,"init","-q"); return r

    def test_project_scope_installs_all_adapters_without_touching_user_hooks(self):
        with tempfile.TemporaryDirectory() as td:
            base=pathlib.Path(td); home=base/"home"; home.mkdir(); repo=self.repo(td)
            # Pre-existing settings prove merge preservation.
            (repo/".cursor").mkdir(); (repo/".cursor/hooks.json").write_text(json.dumps({"version":1,"hooks":{"stop":[{"command":"echo existing"}]}}))
            (repo/".factory").mkdir(); (repo/".factory/hooks.json").write_text(json.dumps({"Custom":[{"hooks":[{"type":"command","command":"echo custom"}]}]}))
            p=run_install(["hooks","--hosts","all","--scope","project","--project-root",str(repo)],home)
            expected=[
                repo/".claude/settings.json", repo/".codex/hooks.json", repo/".grok/hooks/project-context.json",
                repo/".opencode/plugins/project-context.js", repo/".opencode/commands/project-context.md", repo/".cursor/hooks.json", repo/".factory/hooks.json",
                repo/".pi/extensions/project-context.ts", repo/".agents/hooks.json",
                repo/".hermes/plugins/project-context/plugin.yaml", repo/".hermes/plugins/project-context/__init__.py",
                repo/"hooks/project-context/HOOK.md", repo/"hooks/project-context/handler.js",
            ]
            for path in expected: self.assertTrue(path.exists(), path)
            cursor=json.loads((repo/".cursor/hooks.json").read_text()); self.assertIn("echo existing", [h.get("command") for h in cursor["hooks"]["stop"]])
            droid=json.loads((repo/".factory/hooks.json").read_text()); self.assertIn("Custom",droid)
            self.assertFalse((home/".claude/settings.json").exists())
            self.assertFalse((home/".codex/hooks.json").exists())
            self.assertIn("trust",p.stdout.lower())
            self.assertIn('from "node:os"', (repo/"hooks/project-context/handler.js").read_text())

    def test_project_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            base=pathlib.Path(td); home=base/"home"; home.mkdir(); repo=self.repo(td)
            args=["hooks","--hosts","claude,codex,cursor,droid,antigravity","--scope","project","--project-root",str(repo)]
            run_install(args,home); files=[repo/".claude/settings.json",repo/".codex/hooks.json",repo/".cursor/hooks.json",repo/".factory/hooks.json",repo/".agents/hooks.json"]
            first={p:p.read_bytes() for p in files}; run_install(args,home)
            self.assertEqual(first,{p:p.read_bytes() for p in files})

    def test_skill_locations_and_manifest_cover_all_hosts(self):
        data=json.loads((ROOT/"adapters/HOSTS.json").read_text())
        self.assertEqual(set(data["hosts"]),set(HOSTS))
        self.assertEqual(data["version"],"0.4.0")
        for host in HOSTS:
            self.assertIn("primary", data["hosts"][host]["invocation"])
            self.assertIn("startup_injection", data["hosts"][host]["lifecycle"])
            self.assertIn("stop_behavior", data["hosts"][host]["lifecycle"])
            self.assertTrue(data["hosts"][host]["evidence"])

    def test_project_skills_prefer_shared_agents_path_where_supported(self):
        with tempfile.TemporaryDirectory() as td:
            base=pathlib.Path(td); home=base/"home"; home.mkdir(); repo=self.repo(td)
            run_install(["skills","--hosts","all","--scope","project","--project-root",str(repo)],home)
            self.assertTrue((repo/".agents/skills/project-context/SKILL.md").exists())
            self.assertTrue((repo/".claude/skills/project-context/SKILL.md").exists())
            self.assertTrue((repo/".grok/skills/project-context/SKILL.md").exists())
            self.assertTrue((repo/".factory/skills/project-context/SKILL.md").exists())
            self.assertFalse((repo/".opencode/skills/project-context").exists())
            self.assertFalse((repo/".pi/skills/project-context").exists())

    def test_invalid_project_json_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base=pathlib.Path(td); home=base/"home"; home.mkdir(); repo=self.repo(td)
            pth=repo/".cursor/hooks.json"; pth.parent.mkdir(); original="{ broken\n"; pth.write_text(original)
            p=run_install(["hooks","--hosts","cursor","--scope","project","--project-root",str(repo)],home,check=False)
            self.assertNotEqual(p.returncode,0); self.assertEqual(pth.read_text(),original)

if __name__ == "__main__": unittest.main()
