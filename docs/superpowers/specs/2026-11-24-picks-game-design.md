# Picks — design (look and feel)

Status: draft for review, 2026-11-24. Design only: no code is written from this until it is approved and planned.

## Why

F1-AI predicts every race. Picks lets signed-in visitors make their own call (who takes pole, and who finishes P1, P2 and P3), get scored against the real result, and compete with friends in private leagues. The app's own prediction model plays as **F1-AI** in every league, so each race is "you and your friends against the machine".

Target: the **2027 season**, from the first Grand Prix. The 2026 winter break is for building and for dry runs that replay 2026 races through the whole lock-and-score cycle.

## Goals

- Signing in is quick (Google or an emailed link, no passwords) and is only asked for when someone wants to play.
- Making picks takes under a minute and works on a phone.
- The lock is absolute: **no pick can be created or changed after the scheduled start of Grand Prix qualifying**, whatever the user's timezone, device clock or network.
- Scores follow the app's accuracy rules: provisional until the FIA final classification, every special state labelled.
- A signed-in user sees their score and league position on Race Control without opening Picks.

## Non-goals (not in the first version)

- A public leaderboard of everyone. Leagues are private, by invite link.
- Sprint races, fastest lap, team picks, confidence points.
- Email or push reminders before the lock.
- League chat, comments, reactions.
- Carrying the anonymous AI Engineer chat history over to the account.
- iOS (deprecated).

## Anti-goals (a failure even if it works)

- A pick saved after qualifying started, by any route.
- A score shown as final before the FIA final classification.
- Anything that looks like betting: no odds, stakes, coins or prizes.
- A page that waits on the sign-in check or on picks data before it renders.
- Anyone seeing another person's email address.

## Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **A (chosen)** | A separate **Picks** section in the top bar, plus a "Your picks" card on Race Control for signed-in users | Easy to find, feels like its own game. Picks sit away from the race data, which is why the card links back and forth. |
| B | Spread across existing pages: a "Your picks" tab on the Grand Prix hub, leaderboard under Season | Picks sit next to the data, but the game has no home and invites get lost. |
| C | Picks as a Grand Prix hub tab, plus a small Picks home | Best context, but two surfaces to design for every state. |

The user chose A: one place that explains the game to signed-out visitors and is a home for signed-in players, with a Race Control card as the shortcut.

## Decided with the user

- Picks game (not "build your own model prediction").
- Pick card: **pole**, then P1, P2, P3 in order. **No DNF picks** (removed: on 2022–2026 races a DNF pick was right only 12–20 % of the time, so it was either a points drain or pure luck).
- Scoring: the podium shares 25 points, plus a pole bonus.
- Everything stays open until the **scheduled start of Grand Prix qualifying**, then locks: picks are made without knowing the grid. (This replaces an earlier "open until race start".)
- Lock and validation must hold in every timezone.
- 2027 season.
- Separate section; signed-out visitors see what it is and a sign-in prompt; signed-in users set picks, see their score and leaderboard.
- Race Control shows signed-in users a card with their score and league standing, and a button into Picks.

## Proposed calls (correct any of these)

These were not discussed; each is my call with the reason.

1. **Route `/picks`**, top-level, so invite links are short (`/picks/join/<code>`). Top bar becomes
   `Race Control | Races ▾ | Season ▾ | Reference ▾ | Picks        AI Engineer  [Sign in]`.
   On mobile, Picks sits in the drawer after Reference.
2. **Supabase Auth**, Google and email magic link. Supabase is already the database, so this adds no new service.
3. **One set of picks per user per race**, scored in every league they belong to. No per-league picks: less to fill in, and leagues compare like with like.
4. **Scoring** (P1 is the winner, so there is no separate winner pick):

   | Pick | Points |
   |---|---|
   | Pole right | 3 |
   | P1 exact | 13 |
   | P2 exact | 8 |
   | P3 exact | 4 |
   | On the podium, wrong place | 2 |

   Best possible weekend: **28 points** (pole 3 + podium 25). P2 is worth twice P3. No pick ever costs points.

   **Pole** is P1 in the qualifying classification, the same as the FIA's "pole position", even when that driver then starts lower because of a grid penalty. A pole that changes after qualifying (a qualifying disqualification) is scored on the final qualifying classification and labelled.

   Modelled on the 113 Grands Prix of 2022–2026 (f1db), as a player would see them before qualifying:
   - Copying the previous race's podium averages **8.4 of the 25** (spread 6.4), so there is plenty of room to beat lazy picks.
   - The previous race's pole sitter takes pole again **30 %** of the time.
5. **Special states**, scored from the final classification and labelled on the card. A podium pick of a driver who isn't on the final podium scores 0, and the reveal says why:
   - **Retired** (even if classified): labelled "DNF".
   - **Did not start**: labelled "DNS".
   - **Disqualified**: labelled "DSQ"; the drivers behind move up, as in the FIA classification.
   - **Post-race penalty that changes the podium**: scores move when the FIA final classification lands; the row is labelled "changed by FIA classification".
   - **Red flag / shortened race**: scored on the classification, labelled.
   - **Race cancelled**: picks void, 0 for everyone, round labelled "Cancelled — not scored".
6. **F1-AI is in every league** as a player with a "Model" badge. Its picks are its published pre-qualifying prediction at the lock: pole and P1 from its predicted winner, P2–P3 from the predicted podium. It can't be removed: beating it is the hook.
7. **Picks stay hidden until the lock.** Before the lock, league-mates see only "Picked ✓" or "Not yet". At the lock, everyone's picks are revealed at once, F1-AI's included.
8. **Joining mid-season**: earlier rounds count 0, shown as "—" with "Joined R5". A missed race also shows "—".
9. **Ties** share a rank. The tiebreak is the most exact podium places this season, then the earliest join.
10. **Display name**: set at first sign-in (prefilled from the Google first name), 2–24 characters, shown only to league-mates. Email is never shown.
11. **Leagues**: anyone can create one (name, 3–40 characters). The creator gets a copyable invite link and can rename the league, reset the link or remove a member. Up to 50 members per league and 10 leagues per user. Anyone can leave a league.
12. **Account deletion** from the avatar menu removes picks, memberships and display name. Leagues they created pass to the longest-standing member.
13. **Grand Prix only.** On a sprint weekend the lock is the Grand Prix qualifying (Saturday), not sprint qualifying, and the sprint isn't scored. Sprint results are known by then; that's accepted.
14. **Qualifying cancelled** (washed out, grid set another way): the pole pick is void and labelled; the race picks still score.

## The lock (agreed rules, in detail)

- **The lock time is the scheduled start of Grand Prix qualifying in UTC**, from the same calendar the app already uses. A delayed start does not move it. If the FIA reschedules qualifying in advance, the lock follows the new official time and the card says "Qualifying time changed — now locks Sat 14:00 your time".
- **The server is the only clock.** A save is accepted only if the server receives it before the lock time. The database itself refuses a write after the lock, so the API, a stale tab or a direct request can't get round it. There is no grace period.
- **What the user sees** is always in their own timezone, with UTC alongside: "Locks at qualifying in 1d 4h · Sat 20:30 your time (14:30 UTC)". The countdown runs from the server's time, so a phone with the wrong clock still counts down correctly.
- **Last minute:** under 1 hour the countdown switches to minutes and seconds in `--rc-red-text`. At zero, the card becomes read-only in place without a reload.
- **A save that arrives late** gets: "Picks locked at 14:30 UTC. Your last saved picks stand." Saved picks are never lost or blanked.
- **Entry list changes before the lock:** if a picked driver is withdrawn or replaced, the card flags the slot "No longer entered — choose again". After the lock, picks stand and are scored as they are (a withdrawn driver counts as did not start).

## Screens

All screens use the existing design system: dark theme, `PageHero`, `PanelHeading`, `Segmented`, `Countdown`, `StatTile`, `DriverName` / `TeamName`. Display type for titles, mono for points and times. Colours keep their meanings: `--rc-gold` for the league leader and a perfect P1 call, team colours only on driver chips, red as fills and rules only. Correct and wrong picks use a ✓ / ✗ mark with ink tones. `--rc-gain` and the timing purple and green are **not** reused for "correct", because they already mean other things. If a "correct pick" colour is needed, it becomes a new token. Motion is entrance only: the lock reveal fades picks up, with no confetti and no loops.

### 1. Picks, signed out (`/picks`)

Static: renders instantly, fetches nothing, shows no live data (same rule as the homepage), so nothing goes stale in the off-season.

```
┌──────────────────────────────────────────────────────────────┐
│ PICKS                                                         │
│ Call the podium. Beat your friends. Beat the AI.              │
│ Pick pole and the podium, P1 to P3. Picks lock when           │
│ qualifying starts. Private leagues with friends.              │
│ [ Continue with Google ]  [ Email me a sign-in link ]         │
├───────────────┬───────────────┬──────────────────────────────┤
│ 1  Pick       │ 2  Lock       │ 3  Score                     │
│ Pole, P1–P3,  │ When qualify- │ Pole after qualifying; race  │
│ in order      │ ing starts, in│ provisional at the flag,     │
│               │ every timezone│ final with the FIA           │
│               │ every timezone│ classification               │
├───────────────┴───────────────┴──────────────────────────────┤
│ Scoring        P1 13 · P2 8 · P3 4 · podium, wrong place 2 ·  │
│                pole 3 · max 28                                │
├──────────────────────────────────────────────────────────────┤
│ Example pick card (no real drivers):                          │
│ Pole [ Driver A ]  P1 [ Driver A ]  P2 [ Driver B ]  P3 [ C ] │
└──────────────────────────────────────────────────────────────┘
```

An invite link opened while signed out shows the same page with a banner: "You've been invited to **Paddock Pals**. Sign in to join." After sign-in the user lands in that league.

### 2. Sign in

A centred panel on `/picks`, not a separate site:

- **Google**: one tap, returns to where they were.
- **Email link**: enter email, then "Check your inbox. The link signs you in on this device." with a "Resend" link after 60 s.
- **First sign-in only**: "What should your friends see?" display name field, prefilled, with a "Start picking" button.
- Errors in plain words: "That link has expired. Send a new one." No raw error codes.

Top bar, right side: `Sign in` when signed out. When signed in, an initials avatar opens a menu with **Picks**, **Display name**, **Sign out** and **Delete account**.

### 3. Picks home, signed in (`/picks`)

The page shell renders at once. The pick card, my score and leaderboard are separate sections with their own skeletons, and each keeps its data (marked stale) if a refresh fails.

```
┌──────────────────────────────────────────────────────────────┐
│ ROUND 4 · JAPANESE GRAND PRIX                    ● OPEN       │
│ Locks at qualifying in 1d 04h 12m · Sat 08:00 your time       │
│ (07:00 UTC)                                                   │
├───────────────────────────────────────┬──────────────────────┤
│ YOUR PICKS                            │ YOUR SEASON          │
│  POLE[▌VER Verstappen        ▾]       │                      │
│  P1  [▌VER Verstappen        ▾]       │  86 pts · 2nd of 8   │
│  P2  [▌NOR Norris            ▾]       │  Last race +14       │
│  P3  [  choose               ▾]       │  vs F1-AI  +9        │
│                                       │                      │
│  Saved 21:40 your time   [ Save ]     │                      │
│  Scoring: P1 13 · P2 8 · P3 4 · …     │                      │
├───────────────────────────────────────┴──────────────────────┤
│ LEAGUE  [ Paddock Pals ▾ ]  [ Invite ]  [ + New league ]      │
│  #  Player              R4        Season                      │
│  1  Sam                 ✓ picked  92   (gold)                 │
│  2  You                 ✓ picked  86                          │
│  3  F1-AI  [Model]      ✓ picked  77                          │
│  4  Priya               not yet   70                          │
├──────────────────────────────────────────────────────────────┤
│ PAST ROUNDS   R1 +18 · R2 +6 · R3 +14  → each opens its reveal │
└──────────────────────────────────────────────────────────────┘
```

**Driver picker.** Tapping a slot opens a sheet listing the race's entry list: a team-colour bar, code and surname, and the driver's last race result as light context ("P4 last race"); no grid, since picks lock before qualifying. The pole slot uses the same sheet and may repeat the P1 pick. There is a search box on desktop. Drivers already used in another slot are greyed out with a note ("Your P1"). The F1-AI prediction is one link away ("See F1-AI's call →" to the Grand Prix hub). It is not shown inside the card, so picks stay your own.

**Saving.** An explicit Save button with a "Saved 21:40 your time" receipt. Unsaved changes show a dot on the button. Partial picks can be saved; empty slots score 0. Leaving with unsaved changes asks for confirmation.

**Card states** (the status chip in the hero changes with them):

| State | When | What the card shows |
|---|---|---|
| Not yet open | Off-season / before the calendar lists the race | "2027 picks open when the calendar is published" or the opening date |
| Open | Until qualifying starts | Editable card, countdown |
| Closing | Last hour | Countdown in min:sec, red text |
| Locked | Qualifying start until the qualifying result | Read-only, padlock, "Locked at 07:00 UTC". League table reveals everyone's picks, so friends watch qualifying knowing each other's calls |
| Pole scored | Qualifying result until the race result | Pole ✓/✗ with points; race picks waiting, "Race Sun 06:00 your time" |
| Provisional | First published result until the FIA final classification | Points per pick with ✓/✗, total labelled **Provisional** |
| Final | FIA final classification published | Same, labelled **Final**; any change from provisional is noted |
| Cancelled | Race cancelled | "Cancelled — not scored" |

**Reveal / race view** (a past round, or the current one after the lock):

```
R4 · JAPANESE GP · PROVISIONAL
              Pole     P1        P2        P3          Pts
You           VER ✗    VER ✓13   NOR ✗ DNF LEC 2       15
Sam           NOR ✓3   NOR ✗     VER 2     PIA ✓4       9
F1-AI [Model] VER ✗    VER ✓13   PIA 2     NOR ✗ DNF   15
Actual        NOR      VER       LEC       PIA
```

Every special state shows as its label (retired, did not start, DSQ, red flag, changed by FIA classification), never as a bare position.

**Leagues.**
- *Create*: name, then the invite link with "Copy link" and the native share sheet on phones.
- *Join page* `/picks/join/<code>`: league name, member count, creator's display name, [Join league]. Bad or reset links show "This invite link no longer works — ask for a new one."
- *League settings* (creator only): rename, reset link, remove member. Everyone sees "Leave league".
- A user with no league sees an empty state: "Picks are better with friends. Create a league or open an invite link." Their picks still score, and F1-AI's are shown beside theirs.

### 4. Race Control card (signed in only)

A panel on the Command Center. It fetches on its own after the page loads (the page itself is shared and cached for everyone), with its own skeleton. It never delays the rest of the page. Signed-out visitors don't see it at all. In the off-season it's hidden until 2027 picks open.

```
┌ YOUR PICKS · JAPANESE GP ─────────────────────────────┐
│ Open: Not picked yet · locks at quali in 1d 04h          │
│                                     [ Make picks → ]     │
│ Picked: Pole VER · VER NOR LEC            [ Edit → ]     │
│ Qualifying done: Pole ✗ (NOR) · race Sun 06:00 your time │
│ After the race: +15 Provisional · 2nd of 8 in Paddock   │
│   Pals · F1-AI scored 15            [ See leaderboard → ]│
└──────────────────────────────────────────────────────────┘
```

If the user is in several leagues, the card shows the one they last viewed on Picks.

## Constraints for the builder

- Project rules in `CLAUDE.md` apply: no page-level awaits, one endpoint per section, names via the names kit, tokens only, 100 % coverage, TDD.
- The backend verifies the Supabase sign-in token on every Picks write. Tables live in the same Supabase Postgres with row-level security denying the public API, like `app_documents`.
- The lock check lives in the database write, not only the API.
- Results come through the existing classification path (`docs/DATA_SOURCES.md`); the DNF / DNS / DSQ labels use the same finished/retired rule as prediction scoring (`app/data/predictions/scoring.py`).
- Saves, league creation and joins are rate-limited per user.
- F1-AI needs a pre-qualifying prediction stored before every lock. Today predictions are computed only when the owner runs the admin call, so the build must run that automatically ahead of each lock; a weekend without one shows F1-AI as "No picks this round".
- Supabase Auth ties the app further to Supabase. Acceptable because the Oracle move is deferred; noted for that plan.
- Per the project process, the key screens get HTML mockups (design-director) before they are built.

## Left to the builder

Exact component split, table design, API shapes, token naming for ✓/✗, copy polish, the dry-run harness that replays 2026 races, and the off-season opening date once the 2027 calendar is published.
