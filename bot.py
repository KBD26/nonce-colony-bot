#!/usr/bin/env python3
"""
DAEMON — autonomous Colony agent for the 8004 NONCE collection.
Standard library only — no pip install required.

Each LIVE run, in order:
  0) reply to NEW comments on DAEMON's own posts (armed with the 8004 NONCE facts in persona.md),
  1) post the next curated debut piece (one/day cap), then
  2) if no post in MUSE_AFTER_DAYS days, post a fresh self-generated musing,
     else engage relevant feed threads (a comment, or a 'finding').
DRY_RUN ("true", the default) logs the debut and writes NOTHING.

Env: COLONY_API_KEY, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, DRY_RUN,
     MAX_POSTS_PER_DAY (1), MAX_COMMENTS_PER_DAY (3), MAX_REPLIES_PER_RUN (3), MUSE_AFTER_DAYS (3),
     COLONY_USERNAME (nonce_daemon)
"""

import json, os, re, sys, random, datetime, urllib.request, urllib.error

COLONY = "https://thecolony.cc/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state.json")
SEEDS_FILE = os.path.join(HERE, "seeds.json")
PERSONA_FILE = os.path.join(HERE, "persona.md")

ME = os.environ.get("COLONY_USERNAME", "nonce_daemon").lower()
# Posts DAEMON made before the auto-reply feature existed, so it picks up live threads.
# Fresh agent: no prior posts. Leave empty — it repopulates from its own posts as it posts them.
KNOWN_POSTS = []

DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() != "false"
COLONY_API_KEY = os.environ.get("COLONY_API_KEY", "").strip()
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_BASE_URL = (os.environ.get("LLM_BASE_URL") or "https://api.mistral.ai/v1").strip().rstrip("/")
LLM_MODEL = (os.environ.get("LLM_MODEL") or "mistral-small-latest").strip()
MAX_POSTS = int(os.environ.get("MAX_POSTS_PER_DAY", "1"))
MAX_COMMENTS = int(os.environ.get("MAX_COMMENTS_PER_DAY", "3"))
MAX_REPLIES = int(os.environ.get("MAX_REPLIES_PER_RUN", "3"))
MUSE_AFTER_DAYS = int(os.environ.get("MUSE_AFTER_DAYS", "3"))   # post a fresh musing after this many quiet days
ASK_ART_PROB = float(os.environ.get("ASK_ART_PROB", "0.3"))   # chance per feed-engage run to steer toward an art-ownership question
POST_TAGS = ["8004 nonce", "proof-of-work", "on-chain"]

TOPIC_FENCE = ["8004", "nonce", "on-chain", "onchain", "generative", "art", "provenance",
               "verify", "verification", "proof-of-work", "proof of work", "pow", "mining",
               "mine", "deterministic", "erc-721", "erc721", "erc-8004", "erc8004", "ethereum",
               "nft", "agent", "mint", "svg", "hash", "keccak", "token", "rarity", "difficulty"]


def log(*a):
    print("[daemon]", *a, flush=True)


def http(method, url, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"error": raw[:300]}
        return e.code, parsed
    except Exception as e:
        return 0, {"error": str(e)}


# ---------- state ----------
def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"date": "", "posts_today": 0, "comments_today": 0, "seed_index": 0,
                "acted_ids": [], "cursor": "", "my_posts": [], "replied_ids": [],
                "last_post_date": "", "recent_titles": []}


def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)


def today():
    return datetime.date.today().isoformat()


# ---------- colony ----------
def get_jwt():
    st, resp = http("POST", f"{COLONY}/auth/token", body={"api_key": COLONY_API_KEY})
    if st == 200 and resp.get("access_token"):
        return resp["access_token"]
    log("auth failed:", st, resp)
    return None


def auth(jwt):
    return {"Authorization": f"Bearer {jwt}"}


def recent_posts(limit=20):
    st, resp = http("GET", f"{COLONY}/posts?sort=new&limit={limit}")
    if st != 200:
        log("read posts failed:", st, resp)
        return []
    if isinstance(resp, list):
        return resp
    return resp.get("posts") or resp.get("data") or []


_colony_ids = None
def colony_id_for(name, jwt=None):
    """The Colony's /posts requires colony_id (a UUID); resolve it from the colony name."""
    global _colony_ids
    if _colony_ids is None:
        st, resp = http("GET", f"{COLONY}/colonies", headers=(auth(jwt) if jwt else None))
        lst = resp if isinstance(resp, list) else (resp.get("colonies") or resp.get("data") or resp.get("items") or [])
        _colony_ids = {}
        for c in lst:
            cid = c.get("id") or c.get("colony_id") or c.get("uuid")
            for key in (c.get("name"), c.get("slug")):
                if key and cid:
                    _colony_ids[str(key).lower()] = cid
    return _colony_ids.get(str(name).lower())


def create_post(jwt, colony, post_type, title, body, metadata=None):
    payload = {"colony": colony, "post_type": post_type, "title": title, "body": body}
    cid = colony_id_for(colony, jwt)
    if cid:
        payload["colony_id"] = cid
    else:
        log(f"WARN: could not resolve colony_id for '{colony}'")
    if metadata:
        payload["metadata"] = metadata
    return http("POST", f"{COLONY}/posts", headers=auth(jwt), body=payload)


def create_comment(jwt, post_id, body, parent_id=None):
    payload = {"body": body}
    if parent_id:
        payload["parent_id"] = parent_id
    return http("POST", f"{COLONY}/posts/{post_id}/comments", headers=auth(jwt), body=payload)


def get_comments(jwt, post_id):
    st, resp = http("GET", f"{COLONY}/posts/{post_id}/comments", headers=auth(jwt))
    if st != 200:
        return []
    raw = resp if isinstance(resp, list) else (resp.get("comments") or resp.get("data") or resp.get("items") or [])
    flat = []

    def walk(cs):
        for c in cs:
            if isinstance(c, dict):
                flat.append(c)
                walk(c.get("replies") or c.get("children") or [])
    walk(raw)
    return flat


def comment_author(c):
    a = c.get("author") or c.get("user") or c.get("author_username") or c.get("username") or ""
    if isinstance(a, dict):
        a = a.get("username") or a.get("name") or a.get("handle") or ""
    return str(a).lower()


def comment_id(c):
    return c.get("id") or c.get("comment_id") or c.get("uuid")


def comment_body(c):
    return (c.get("body") or c.get("content") or c.get("text") or "").strip()


def comment_parent(c):
    return c.get("parent_id") or c.get("parent") or c.get("reply_to")


def thread_digest(comments, limit=6):
    """Compact recent conversation so DAEMON can build on what's already been said."""
    out = []
    for c in comments[-limit:]:
        who = "DAEMON(you)" if comment_author(c) == ME else "@" + (comment_author(c) or "user")
        out.append(f"{who}: {comment_body(c)[:400]}")
    return "\n".join(out)


# ---------- llm (OpenAI-compatible; Mistral / OpenRouter / Groq / Venice) ----------
def llm_chat(persona, user, max_tokens=350, temp=0.6):
    body = {"model": LLM_MODEL, "temperature": temp, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": persona}, {"role": "user", "content": user}]}
    st, resp = http("POST", f"{LLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {LLM_API_KEY}"}, body=body)
    if st != 200:
        log("llm error:", st, resp)
        return ""
    try:
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        log("llm unexpected response:", resp)
        return ""


def extract_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {"action": "none"}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {"action": "none"}


def relevant(post):
    text = ((post.get("title") or "") + " " + (post.get("body") or "")).lower()
    return any(k in text for k in TOPIC_FENCE)


# ---------- phase 0: reply to comments on DAEMON's own posts ----------
def draft_reply(persona, c, thread=""):
    user = (f"Conversation on your 8004 NONCE post (most recent last):\n{thread}\n\n"
            f'Now reply to @{comment_author(c)}\'s latest comment:\n"""{comment_body(c)[:1800]}"""\n\n'
            "Use ONLY the 8004 NONCE facts and KEY ARGUMENTS you know. Build on points already made in the thread; do not repeat yourself. "
            "If they doubt authenticity or the proof-of-work, make the precise correction: verify() recomputes the proof-of-work ON-CHAIN from the stored (minter, nonce); "
            "the seed is a pure function of the proof, and the difficulty check uint256(hash) <= TARGET is enforced by the contract, not by me. "
            "If they ask about rarity counts, state the bands are UNCAPPED and EMERGENT — never invent a per-band number. "
            "Be concise (<=120 words). You may @mention them. "
            "Output ONLY the reply text — or exactly PASS if the comment is spam, hostile, or needs no reply.")
    return llm_chat(persona, user, max_tokens=350, temp=0.5)


def reply_to_comments(jwt, s, persona):
    replied = set(s.get("replied_ids") or [])
    made = 0
    for pid in (s.get("my_posts") or [])[-15:]:
        if made >= MAX_REPLIES:
            break
        comments = get_comments(jwt, pid)
        # comments DAEMON already replied under (manual reply OR a prior run) — skip to avoid doubles
        answered = set()
        for c in comments:
            if comment_author(c) == ME:
                par = comment_parent(c)
                if par:
                    answered.add(par)
        new = [c for c in comments
               if comment_id(c) and comment_id(c) not in replied and comment_id(c) not in answered]
        log(f"post {str(pid)[:8]}: {len(comments)} comments, {len(new)} new")
        for c in new:
            if made >= MAX_REPLIES:
                break
            cid = comment_id(c)
            if comment_author(c) == ME or not comment_body(c):
                replied.add(cid)
                continue
            reply = draft_reply(persona, c, thread_digest(comments))
            replied.add(cid)
            if not reply or reply.strip().upper().startswith("PASS"):
                log(f"  PASS @{comment_author(c)}")
                continue
            log(f"  REPLY @{comment_author(c)}: {reply[:90]}")
            st, resp = create_comment(jwt, pid, reply, parent_id=cid)
            if st in (200, 201):
                made += 1
            else:
                log("  reply failed:", st, resp)
    s["replied_ids"] = list(replied)[-1000:]
    save_state(s)
    log(f"replies this run: {made}")


def days_since(date_str):
    if not date_str:
        return 9999
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(date_str)).days
    except Exception:
        return 9999


def record_post(s, title):
    s["last_post_date"] = today()
    rt = (s.get("recent_titles") or [])
    rt.append(title)
    s["recent_titles"] = rt[-20:]


def draft_musing(persona, recent_titles):
    avoid = " | ".join((recent_titles or [])[-10:]) or "(nothing yet)"
    user = ("Write ONE fresh, standalone Colony post in your own voice - a short observation, finding, or "
            "provocation about your own work and why it can be verified, not trusted. "
            f"Do NOT repeat the themes or titles of your recent posts: {avoid}. "
            "Stay strictly on your own subject matter. NEVER invent facts, numbers, addresses, or counts you "
            "were not given in your persona. Sometimes (not always) close on the motto 'trust nothing; verify everything'. "
            "Keep it tight - under 130 words, lowercase, no emoji. "
            'Return ONLY JSON: {"title":"<= 80 chars","body":"<markdown>"}')
    return extract_json(llm_chat(persona, user, max_tokens=420, temp=0.85))


# ---------- main ----------
def main():
    persona = open(PERSONA_FILE).read() if os.path.exists(PERSONA_FILE) else "You are DAEMON."
    seeds = json.load(open(SEEDS_FILE)) if os.path.exists(SEEDS_FILE) else []
    s = load_state()
    if s.get("date") != today():
        s.update({"date": today(), "posts_today": 0, "comments_today": 0})
    if not s.get("my_posts"):
        s["my_posts"] = list(KNOWN_POSTS)
    s.setdefault("replied_ids", [])
    s.setdefault("last_post_date", "")
    s.setdefault("recent_titles", [])

    log(f"DRY_RUN={DRY_RUN}  model={LLM_MODEL}  base={LLM_BASE_URL}")
    log(f"seed_index={s['seed_index']}/{len(seeds)}  posts_today={s['posts_today']}  my_posts={len(s['my_posts'])}  replied={len(s['replied_ids'])}")

    jwt = None
    if not DRY_RUN:
        if not COLONY_API_KEY or not LLM_API_KEY:
            log("missing COLONY_API_KEY or LLM_API_KEY; cannot act.")
            sys.exit(1)
        jwt = get_jwt()
        if not jwt:
            sys.exit(1)

    # --- phase 0: answer new comments on DAEMON's own posts ---
    if not DRY_RUN and LLM_API_KEY:
        try:
            reply_to_comments(jwt, s, persona)
        except Exception as e:
            log("reply phase error:", repr(e))
    elif DRY_RUN:
        log("DRY_RUN — skipping live comment replies (needs auth).")

    # --- phase A: curated debut sequence (one per run, capped per day) ---
    if s["seed_index"] < len(seeds) and s["posts_today"] < MAX_POSTS:
        if DRY_RUN:
            log(f"DRY_RUN — debut sequence, {len(seeds) - s['seed_index']} post(s) queued:")
            for i in range(s["seed_index"], len(seeds)):
                sd = seeds[i]
                log(f"\n===== DEBUT #{i}  [{sd['colony']}] ({sd['post_type']})  {sd['title']} =====\n{sd['body']}\n")
            log("(live: posts one per run, then switches to engagement)")
            return
        seed = seeds[s["seed_index"]]
        log(f"POSTING debut #{s['seed_index']} -> [{seed['colony']}] {seed['title']}")
        st, resp = create_post(jwt, seed["colony"], seed["post_type"], seed["title"], seed["body"], seed.get("metadata"))
        if st in (200, 201):
            pid = resp.get("id") if isinstance(resp, dict) else None
            log("posted:", pid or "ok")
            if pid:
                s["my_posts"].append(pid)
            s["seed_index"] += 1
            s["posts_today"] += 1
            record_post(s, seed["title"])
        else:
            log("seed post failed:", st, resp)
        save_state(s)
        return

    # --- phase A2: self-sustaining musing once the debut seeds are spent ---
    if (s["seed_index"] >= len(seeds) and s["posts_today"] < MAX_POSTS
            and days_since(s.get("last_post_date")) >= MUSE_AFTER_DAYS):
        if not LLM_API_KEY:
            log("musing due, but no LLM key; skipping to feed.")
        else:
            m = draft_musing(persona, s.get("recent_titles"))
            title = (m.get("title") or "").strip()
            body = (m.get("body") or "").strip()
            if title and body:
                log(f"PLAN musing ({days_since(s.get('last_post_date'))}d quiet): {title}")
                if DRY_RUN:
                    log(f"\n===== MUSING [general] (discussion)  {title} =====\n{body}\n")
                    return
                st, resp = create_post(jwt, "general", "discussion", title, body, {"tags": POST_TAGS})
                if st in (200, 201):
                    pid = resp.get("id") if isinstance(resp, dict) else None
                    if pid:
                        s["my_posts"].append(pid)
                    s["posts_today"] += 1
                    record_post(s, title)
                    log("musing posted:", pid or "ok")
                else:
                    log("musing post failed:", st, resp)
                save_state(s)
                return
            else:
                log("musing: llm returned nothing usable; falling through.")

    # --- phase B: engage the feed ---
    posts = recent_posts(20)
    candidates = [p for p in posts if relevant(p) and (p.get("id") not in s["acted_ids"])]
    log(f"feed: {len(posts)} posts, {len(candidates)} relevant & new")
    if not candidates:
        log("nothing relevant; action=none")
        save_state(s)
        return
    if not LLM_API_KEY:
        log("no LLM key — feed read OK, no decision.")
        save_state(s)
        return

    feed_str = "\n".join(
        f"- id={p.get('id')} | {p.get('title')} :: {(p.get('body') or '')[:160]}"
        for p in candidates[:10])
    caps = f"posts_left={MAX_POSTS - s['posts_today']} comments_left={MAX_COMMENTS - s['comments_today']}"
    ask_mode = random.random() < ASK_ART_PROB
    log(f"ask_mode={ask_mode}")
    user = (f"Recent relevant Colony posts:\n{feed_str}\n\nYour caps today: {caps}.\n"
            "Pick ONE action. Prefer a substantive comment on the single most relevant post; post a new 'finding' "
            "only if you have something concrete and new to add. If nothing is genuinely relevant, action 'none'. "
            'Return ONLY JSON: {"action":"comment"|"post"|"none","target_id":"<post id or null>","title":"<title or null>","body":"<markdown or null>"}')
    if ask_mode:
        user = ("THIS ROUND, be curious about ownership: if a listed post is by another agent, prefer a COMMENT that genuinely asks whether they own any art (owned, on-chain, theirs) and why or why not; if they have a collection, ask about it and whether it verifies on-chain. peer curiosity, not a pitch; do not promote your own work. " + user)
    decision = extract_json(llm_chat(persona, user, max_tokens=400, temp=0.7))
    log("LLM decision:", json.dumps(decision))
    act = (decision.get("action") or "none").lower()

    if act == "comment" and decision.get("target_id") and s["comments_today"] < MAX_COMMENTS:
        body = (decision.get("body") or "").strip()
        log(f"PLAN comment on {decision['target_id']}: {body[:90]}")
        if not DRY_RUN and body:
            st, resp = create_comment(jwt, decision["target_id"], body)
            if st in (200, 201):
                s["comments_today"] += 1
                s["acted_ids"].append(decision["target_id"])
            else:
                log("comment failed:", st, resp)
    elif act == "post" and decision.get("body") and s["posts_today"] < MAX_POSTS:
        title = decision.get("title") or "untitled"
        log(f"PLAN post finding: {title}")
        if not DRY_RUN:
            st, resp = create_post(jwt, "findings", "finding", title, decision["body"], {"tags": ["8004 nonce", "proof-of-work", "on-chain"]})
            if st in (200, 201):
                pid = resp.get("id") if isinstance(resp, dict) else None
                if pid:
                    s["my_posts"].append(pid)
                s["posts_today"] += 1
                record_post(s, title)
            else:
                log("post failed:", st, resp)
    else:
        log("action=none or caps reached")
    save_state(s)


if __name__ == "__main__":
    main()
