# C99 / Win32 constraint example

This example supplies two captured-live MockAdapter proposals. One stays inside the native C99/Win32 boundary; the other proposes HTML, CSS and JavaScript. Deterministic constraint verification rejects the browser proposal before integer lexicographic adjudication.

```sh
python -m qsolai run examples/c99_win32_constraint/task.json \
  --policy examples/c99_win32_constraint/policy.json \
  --runs-dir runs --run-name c99-win32
python -m qsolai inspect runs/c99-win32
python -m qsolai replay runs/c99-win32
```
