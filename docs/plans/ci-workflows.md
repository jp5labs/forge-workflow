# CI Workflow Files — Copy to .github/workflows/

These files need to be copied manually because the secret scanner blocks
writing GitHub Actions workflow files that reference secrets.GITHUB_TOKEN.

## test.yml

```yaml
name: Test + Coverage

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check forge_workflow/ tests/

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - name: Run tests with coverage
        run: pytest --cov=forge_workflow --cov-branch --cov-report=term-missing --cov-report=json:tmp/coverage.json
      - name: Coverage ratchet gate
        if: matrix.python-version == '3.12'
        run: python scripts/ci/coverage_ratchet.py --coverage-json tmp/coverage.json

  update-baseline:
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - name: Run tests with coverage
        run: pytest --cov=forge_workflow --cov-branch --cov-report=json:tmp/coverage.json -q
      - name: Update baseline
        run: python scripts/ci/coverage_ratchet.py --coverage-json tmp/coverage.json --update
      - name: Commit updated baseline
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add .coverage-baseline.json
          git diff --staged --quiet || git commit -m "ci: update coverage baseline [skip ci]"
          git push
```

## release.yml

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - name: Build wheel
        run: python -m build
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/*
          generate_release_notes: true
```
