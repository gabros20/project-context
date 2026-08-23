# Releasing project-context

Releases are created from signed semantic-version tags after the tagged source passes the complete test and release-contract checks.

## Prepare a release

1. Choose `X.Y.Z` according to semantic versioning.
2. Update `PACKAGE_VERSION` in `scripts/install.py`.
3. Update `DEFAULT_VERSION` in both `site/install.sh` and `site/install.ps1`.
4. Add a dated `## X.Y.Z - YYYY-MM-DD` section to `CHANGELOG.md`.
5. Update the current package version in `README.md` and any versioned bundle documentation.

Verify the synchronized declarations and test the repository:

```bash
python3 scripts/check_release.py vX.Y.Z
sh -n site/install.sh
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/ctx.py scripts/install.py scripts/check_release.py
git diff --check
```

## Publish

Commit and push the release preparation to `main`, then create and push a signed annotated tag:

```bash
git tag -s vX.Y.Z -m "project-context X.Y.Z"
git push origin vX.Y.Z
```

The tag-triggered `Release` workflow repeats the contract and test checks, then creates the GitHub Release only if the remote tag already exists. GitHub-generated source archives are the release artifacts used by the bootstrap installer.

Verify the published release:

```bash
gh release view vX.Y.Z
curl -fsSL https://project-context-mu.vercel.app/install.sh | sh
```

Do not move or reuse a published tag. Prepare a new patch release instead.
