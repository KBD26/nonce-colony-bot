# 8004 NONCE agent — setup (reuses the KOINE daemon-colony-bot)

Same architecture as your KOINE agent (`daemon-colony-bot/`): stdlib Python + GitHub Actions cron + Mistral + The Colony, driven by `persona.md` + `seeds.json`. Only the content, the Colony handle, and the contract facts change — `bot.py` is collection-agnostic.

## Stand it up
1. **New repo** — copy `daemon-colony-bot/` to a new repo (e.g. `nonce-colony-bot`) under your GitHub (KBD26). Keep `bot.py` + `.github/workflows/`.
2. **Swap in these two files** — replace `persona.md` and `seeds.json` with the ones in this folder.
3. **Clear KOINE-specific constants in `bot.py`** — empty/replace `KNOWN_POSTS` (it repopulates from the new agent's own posts) and update any hardcoded KOINE handle/colony defaults. Don't touch the logic.
4. **New Colony agent** — under your human account (the one that runs @koine_daemon), create a NEW agent: handle e.g. `nonce_daemon` (lowercase), display **DAEMON**, avatar = an 8004 NONCE piece (e.g. #0). Copy its `col_…` API key (shown once).
5. **GitHub Secrets** on the new repo: `MISTRAL_API_KEY` (reuse), `COLONY_API_KEY` (the new agent's `col_` key). Repo Variable `DRY_RUN` = `true`.
6. **Dry-run** via Actions → confirm the debut prints → set `DRY_RUN=false` to go live. Cadence `MAX_POSTS_PER_DAY=1`: intro → finding → challenge → the rarity question, with feed engagement between (use the **Run workflow** button, never "Re-run jobs").

## The subtle-clue layer (what you asked for)
- It lives in two places: the **4th seed** in `seeds.json` ("a question about rarity" — posts last, after the substance) and the **THE QUESTION** section in `persona.md` (lets DAEMON drop a rare cryptic line in feed replies).
- Rule baked into the persona: state the disclosed facts (bands are **uncapped + emergent**) if asked directly, but **never** editorialize which band ends up scarce or explain that the labels can invert. Subtle, sparse, never a signature. Explaining it kills the experiment.

## Guardrail (the KOINE lesson)
`persona.md` is armed with the full FACTS sheet + "answer only from FACTS; never invent counts; prefer PASS over a guess." This is the fix for the KOINE incident where the small model improvised a false "unbounded supply" claim. The rarity FACT is written so it states "uncapped/emergent" — never a fabricated per-band number.

## Timing
Bring the agent live **around `openPublic`** (the announcement). Pre-open it can post the intro/finding/challenge (the collection + genesis are real and verifiable) but must not promise a public-mint date.

## Optional later (mirror KOINE)
- An **8004 NONCE MCP server** (clone `koine-mcp-server`) exposing `nonce_info / nonce_get_piece / nonce_verify` that read the live contract — then point the **ERC-8004 agent card** (`../8004-NONCE-l1/agent-card.md`, already wired to 8004nonce.eth.limo) at it. For launch, the agent already points to the contract + the mint page + `spec.json`.
