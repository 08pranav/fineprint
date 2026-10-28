# Master prompt for Claude Code (cloud)

How to use this:

1. Create an empty GitHub repository (for example `fineprint`).
2. Put the project in it, either way:
   - **Easiest:** on the repository page choose *Add file > Upload files*, drop `fineprint.zip`, and commit.
   - **Or:** unzip locally, then `git init`, `git add .`, `git commit -m "FinePrint"`, `git push`.
3. Open Claude Code on the web, start a session on that repository, and paste everything below the line.

---

You are working in the FinePrint repository: a Python (FastAPI) and plain-JavaScript web app that reads Indian loan, credit card, pay-later and insurance documents, flags risky clauses, converts them to rupees with a deterministic calculator, and answers questions in English, Hindi, Marathi and Hinglish. It is a university NLP project for a team of two. Your job is to get it into the repository in working order, verify it, push it, and make it ready to deploy. Do not redesign it.

## 1. Unpack if needed

If the repository root contains `fineprint.zip` and no `src/` folder, unzip it so that `src/`, `web/`, `data/`, `tests/`, `eval/`, `Dockerfile` and `README.md` sit at the repository root (strip a single top-level `fineprint/` folder if the zip has one). Delete the zip. Commit: `Add FinePrint source`.

## 2. Read before changing anything

Read `README.md`, `docs/PROJECT_GUIDE.md` (if present), `src/fineprint/schemas.py`, `src/fineprint/risk/pipeline.py` and `src/fineprint/service.py`. Follow these project rules throughout:

- The language model never does arithmetic. Rupee figures come only from `src/fineprint/calc/impact.py`.
- Every risk flag must quote text that exists in the document (`risk/verify.py`). Do not loosen this.
- The app must work with no API key (rules-only mode). Tests must never need network access or a key.
- Never commit secrets, `.env`, or real user documents. `data/real/` stays out of git.
- Never edit `data/eval/gold.json` to raise a score, and never tune rules using the `test` split.
- Keep the UI's usability rules: visible feedback for every action, inline errors next to their field that keep user input, 44 px touch targets, visible keyboard focus, status never shown by colour alone, works at 360 px width, browser back button works.

## 3. Verify

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
python eval/run_eval.py --methods rules
node --check web/app.js
PYTHONPATH=src uvicorn fineprint.api:app --port 8000 &
sleep 3
curl -sf localhost:8000/api/health
curl -sf localhost:8000/ | grep -q FinePrint && echo "UI served"
curl -sf -F "text=$(cat data/samples/s01_personal_loan.txt)" localhost:8000/api/extract | head -c 300
```

Expected: all tests pass (52 at handover), rules-only F1 about 0.84 on the test split, health returns `"mode":"rules"`, and the extract call returns masked text with `[PAN]` and a clause count. If Docker is available, also run `docker build -t fineprint .` and the container smoke test from `.github/workflows/ci.yml`.

If something fails, find the root cause and fix it in the smallest way that respects the rules above. Do not delete or weaken tests to make them pass. Explain each fix in its commit message.

## 4. Optional: evaluate with a language model

Only if the environment has `LLM_API_KEY`, `LLM_MODEL` (and `LLM_BASE_URL` if not OpenAI) set: run `python eval/run_eval.py`, which also scores `llm` and `hybrid`. Commit the updated `eval/results.md` and `eval/results.json` with the message `Evaluation with <model name>`. Never write the key into any file.

## 5. Push

Commit any remaining changes with clear messages and push to `main`. If `main` is protected, push a branch named `setup/fineprint` and open a pull request titled `FinePrint: verified and ready to deploy`, with the test count and the evaluation table in the description.

## 6. Prepare deployment

The repository already contains `Dockerfile`, `render.yaml` and `.github/workflows/ci.yml`. Confirm the CI workflow file is valid YAML and that the Dockerfile copies `src`, `web` and `data`. Do not add other hosting configs unless asked.

## 7. Report back

Reply with:

1. What you unpacked and committed (commit hashes).
2. Test results and the evaluation table.
3. Anything you fixed, and why.
4. Deployment steps for the owner, exactly:
   - On render.com: New > Blueprint > choose this repository > Apply.
   - In the service's Environment tab, optionally set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`, then redeploy.
   - Open the service URL; the header should say "Rules + language model" if the key works, or "Rules only" without one.
5. Anything you noticed but did not change.
