# Repository Guidelines

- Routine changes are committed and pushed directly to `main`. Use a feature
  branch for large changes.
- Create a pull request only when the user explicitly requests one. Otherwise,
  merge feature branches directly into `main` after verifying the changes and branch CI.
- Run checks relevant to the change before pushing, and confirm CI succeeds
  after pushing.
- Production deployment is an explicit operator action after CI passes.
