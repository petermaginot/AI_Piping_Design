"""Repo policy checks: the skills, docs and manifests agree with each other.

Pure stdlib; needs neither FreeCAD nor Quetzal.  Run from the repo root:

    python -m unittest discover -s tests
"""
import json
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")

# Every tracked file must stay under this.  Two existing source files (a mesh
# and an annotated photo PDF) are larger; they are listed so that nothing new
# of that size slips in unnoticed.
MAX_BYTES = 5 * 1024 * 1024
LARGE_FILE_ALLOWLIST = {
    "examples/mesh_example/Piping_Model_2.glb",
    "examples/photo_example/Annotoated_photo_1.pdf",
}

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SECTION_REF_RE = re.compile(r"§(\d+(?:\.\d+)*)")
HEADING_NUM_RE = re.compile(r"^#{1,6}\s+(\d+(?:\.\d+)*)\.?\s", re.M)


def skill_names():
    return sorted(d for d in os.listdir(SKILLS)
                  if os.path.isfile(os.path.join(SKILLS, d, "SKILL.md")))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    return fields


def strip_code(text):
    """Drop fenced code blocks and inline code: links in them are not links."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def skill_md_files(skill):
    out = []
    for dirpath, _, files in os.walk(os.path.join(SKILLS, skill)):
        out += [os.path.join(dirpath, f) for f in files if f.endswith(".md")]
    return sorted(out)


def repo_files():
    """Tracked files plus untracked ones that are not ignored: what could be
    committed next.  Falls back to a walk if git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT, capture_output=True, check=True).stdout
        return [p for p in out.decode("utf-8").split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        files = []
        for dirpath, dirs, names in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "private", "__pycache__")]
            files += [os.path.relpath(os.path.join(dirpath, n), ROOT).replace(os.sep, "/")
                      for n in names]
        return files


class SkillStructure(unittest.TestCase):

    def test_frontmatter(self):
        for name in skill_names():
            fm = frontmatter(read(os.path.join(SKILLS, name, "SKILL.md")))
            with self.subTest(skill=name):
                self.assertIsNotNone(fm, "SKILL.md has no frontmatter")
                self.assertEqual(fm.get("name"), name, "frontmatter name != folder name")
                self.assertTrue(fm.get("description"), "frontmatter has no description")

    def test_no_orphan_references(self):
        """Every file in references/ is named somewhere else in its skill,
        so the agent can find it."""
        for name in skill_names():
            ref_dir = os.path.join(SKILLS, name, "references")
            if not os.path.isdir(ref_dir):
                continue
            docs = {p: read(p) for p in skill_md_files(name)}
            for ref in sorted(os.listdir(ref_dir)):
                ref_path = os.path.join(ref_dir, ref)
                mentioned = any(ref in text for p, text in docs.items() if p != ref_path)
                with self.subTest(skill=name, ref=ref):
                    self.assertTrue(mentioned, "not referenced from any other file in the skill")

    def test_section_refs_resolve(self):
        """A "§9.2.2" names a numbered heading in its own skill, or in a
        skill named in the same paragraph ("see `quetzal-piping` §9.6")."""
        defined = {}
        for name in skill_names():
            nums = set()
            for p in skill_md_files(name):
                nums.update(HEADING_NUM_RE.findall(read(p)))
            defined[name] = nums
        for name in skill_names():
            for p in skill_md_files(name):
                text = re.sub(r"```.*?```", "", read(p), flags=re.S)
                for para in re.split(r"\n\s*\n", text):
                    scope = [name] + [s for s in defined if s != name and s in para]
                    for ref in SECTION_REF_RE.findall(para):
                        with self.subTest(file=os.path.relpath(p, ROOT), ref="§" + ref):
                            self.assertTrue(any(ref in defined[s] for s in scope),
                                            "no heading %s in %s" % (ref, ", ".join(scope)))


class Links(unittest.TestCase):

    def test_relative_links_resolve(self):
        docs = [os.path.join(ROOT, "README.md"), os.path.join(ROOT, "AGENTS.md")]
        for name in skill_names():
            docs += skill_md_files(name)
        for doc in docs:
            for target in LINK_RE.findall(strip_code(read(doc))):
                if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                    continue
                path = os.path.normpath(os.path.join(os.path.dirname(doc),
                                                     target.split("#")[0]))
                with self.subTest(doc=os.path.relpath(doc, ROOT), link=target):
                    self.assertTrue(os.path.exists(path), "broken link")

    def test_every_skill_is_listed(self):
        """README and AGENTS.md link every skill, and nothing that isn't one."""
        names = set(skill_names())
        for doc in ("README.md", "AGENTS.md"):
            linked = set(re.findall(r"skills/([\w-]+)/SKILL\.md", read(os.path.join(ROOT, doc))))
            with self.subTest(doc=doc):
                self.assertEqual(linked, names)

    def test_readme_skill_count(self):
        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        n = len(skill_names())
        for m in re.finditer(r"\b(\w+) (?:\[)?agent skills", read(os.path.join(ROOT, "README.md"))):
            word = m.group(1).lower()
            if word in words:
                self.assertEqual(words[word], n, "README says %s agent skills" % word)


class Manifests(unittest.TestCase):

    def test_plugin_manifests(self):
        plugin = json.loads(read(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
        market = json.loads(read(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+$", plugin.get("version", "")))
        names = [p["name"] for p in market["plugins"]]
        self.assertIn(plugin["name"], names)
        for p in market["plugins"]:
            if "version" in p:
                self.assertEqual(p["version"], plugin["version"])


class Evals(unittest.TestCase):
    """examples/*/expected.json, read by tests/eval_live.py in the session."""

    def test_expected_files(self):
        keys = {"case", "source", "reference", "parts", "pipe_length",
                "joints", "joints_failing", "open_ends", "end_spans"}
        ex = os.path.join(ROOT, "examples")
        for case in sorted(os.listdir(ex)):
            path = os.path.join(ex, case, "expected.json")
            if not os.path.isfile(path):
                continue
            data = json.loads(read(path))
            with self.subTest(case=case):
                self.assertEqual(set(data), keys)
                self.assertEqual(data["case"], case)
                self.assertTrue(os.path.isfile(os.path.join(ex, case, data["reference"])))
                self.assertEqual(data["joints_failing"], 0, "reference model has open joints")
                n = data["open_ends"]
                self.assertEqual(len(data["end_spans"]), n * (n - 1) // 2)


class PublicRepo(unittest.TestCase):
    """AGENTS.md: this repo is public.  Keep private material out."""

    def test_nothing_under_private(self):
        leaked = [p for p in repo_files() if p.startswith("private/")]
        self.assertEqual(leaked, [])

    def test_file_size(self):
        for p in repo_files():
            full = os.path.join(ROOT, p)
            if p in LARGE_FILE_ALLOWLIST or not os.path.isfile(full):
                continue
            with self.subTest(file=p):
                self.assertLessEqual(os.path.getsize(full), MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
