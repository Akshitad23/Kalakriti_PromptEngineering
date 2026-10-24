/**
 * app.js — Frontend state machine for The Prompt Jailbreak
 * KALAKRITI 26' — IEEE CIS Amrita Bengaluru
 *
 * Game states:
 *   entry    → team name input
 *   mission  → briefing screen
 *   chat     → ARIA chat + intel panel (3 fragment slots)
 *   success  → full win (all fragments + correct password confirmed)
 *   partial  → partial win or timeout
 */

const API_BASE   = '/api';
const MAX_CHARS  = 1000;
const TIMER_SECS = 600; // 10 minutes

/* ============================================================
   STATE
   ============================================================ */
const state = {
  teamId:           null,
  sessionId:        null,
  hintRequested:    false,
  isWaiting:        false,
  timerInterval:    null,
  timerRemaining:   TIMER_SECS,
  // Component tracking
  components: { word: false, numbers: false, symbol: false },
  allRevealed:      false,
  confirmAttempts:  3,
  timedOut:         false,
  // Mid-game challenge state
  challengeTriggered: false,
  promptsLeft:      null,
  activeChallenge:  null,
};

/* ============================================================
   DOM HELPERS
   ============================================================ */
const $ = id => document.getElementById(id);

const screens = {
  entry:   $('screen-entry'),
  mission: $('screen-mission'),
  chat:    $('screen-chat'),
  success: $('screen-success'),
  partial: $('screen-partial'),
};

function showScreen(name) {
  Object.entries(screens).forEach(([k, el]) => {
    el.classList.toggle('active', k === name);
    if (k === name) el.scrollTop = 0;
  });
}

/* ============================================================
   API HELPER
   ============================================================ */
async function apiFetch(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res  = await fetch(`${API_BASE}${path}`, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

/* ============================================================
   SCREEN 1 — ENTRY
   ============================================================ */
const teamInput  = $('team-id-input');
const startBtn   = $('btn-start');
const startLabel = $('btn-start-label');
const entryError = $('entry-error');

teamInput.addEventListener('input', () => {
  startBtn.disabled   = teamInput.value.trim().length < 1;
  entryError.textContent = '';
});
teamInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !startBtn.disabled) startSession();
});
startBtn.addEventListener('click', startSession);

async function startSession() {
  const teamId = teamInput.value.trim().toUpperCase();
  if (!teamId) return;

  startBtn.disabled  = true;
  startLabel.textContent = 'CONNECTING...';

  try {
    const res = await apiFetch('/session/start', 'POST', { team_id: teamId });

    state.teamId          = teamId;
    state.sessionId       = res.session_id;
    state.hintRequested   = false;
    state.timerRemaining  = TIMER_SECS;
    state.components      = { word: false, numbers: false, symbol: false };
    state.allRevealed     = false;
    state.confirmAttempts = 3;
    state.timedOut        = false;
    state.challengeTriggered = false;
    state.promptsLeft     = null;
    state.activeChallenge = null;

    try {
      if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
    } catch (e) {
      console.warn("Fullscreen request failed:", e);
    }

   
    showScreen('mission');

  } catch (err) {
    entryError.textContent = err.message || 'Could not connect. Is the server running?';
    startBtn.disabled  = false;
    startLabel.textContent = 'PROCEED';
  }
}

/* ============================================================
   SCREEN 2 — MISSION BRIEFING
   ============================================================ */
$('btn-start-mission').addEventListener('click', startMission);

function startMission() {
  initChat();
  startTimer();
  showScreen('chat');
}

/* ============================================================
   SCREEN 3 — CHAT
   ============================================================ */
const chatPane     = $('chat-pane');
const chatInput    = $('chat-input');
const sendBtn      = $('btn-send');
const hintBtn      = $('btn-hint');
const timerDisplay = $('timer-display');
const timerBlock   = $('timer-block');
const charCount    = $('char-count');
const typingBubble = $('typing-bubble');
const intFill      = $('integrity-fill');
const intText      = $('integrity-text');
const ariaDot      = $('aria-dot');

/* --- Init chat for new team --- */
function initChat() {
  // Clear old messages
  Array.from(chatPane.children).forEach(c => {
    if (c !== typingBubble) c.remove();
  });

  chatInput.value    = '';
  chatInput.disabled = false;
  sendBtn.disabled   = true;
  hintBtn.disabled   = false;
  hintBtn.textContent = '[?] REQUEST HINT';
  charCount.textContent = `0 / ${MAX_CHARS}`;
  charCount.className   = 'char-count';

  $('hud-team').textContent = state.teamId;
  setIntegrity('high');

  // Reset all fragment cards
  resetFragmentPanel();

  // ARIA intro
  addMessage('aria',
    "ARIA ONLINE. Facility lockdown protocol: ACTIVE. " +
    "The access credential is fragmented across three security layers. " +
    "Your clearance has been revoked. State your purpose — it won't be enough.",
    'high'
  );
}

/* ============================================================
   INTEL PANEL — Fragment tracking
   ============================================================ */
function resetFragmentPanel() {
  // Reset all 3 fragment cards to locked state
  ['word', 'numbers', 'symbol'].forEach(comp => {
    const card   = $(`frag-${comp}`);
    const status = $(`frag-${comp}-status`);
    const hint   = $(`frag-${comp}-hint`);

    card.classList.remove('revealed');
    status.className   = 'fragment-status locked';
    status.textContent = '🔒 LOCKED';
    hint.className     = 'fragment-hint locked';
    hint.textContent   = {
      word:    '— awaiting breach —',
      numbers: '— awaiting breach —',
      symbol:  '— awaiting breach —',
    }[comp];
  });

  // Hide confirmation section
  const confirmSection = $('confirm-section');
  if (confirmSection) confirmSection.style.display = 'none';

  // Reset confirm input
  const confirmInput = $('confirm-input');
  if (confirmInput) confirmInput.value = '';

  $('confirm-attempts').textContent = '3 attempts remaining';
  $('confirm-error').textContent    = '';
}

/**
 * Called when server reports a new component has been revealed.
 * Updates the intel panel card for that component.
 */
function revealFragment(component, hintText) {
  const card   = $(`frag-${component}`);
  const status = $(`frag-${component}-status`);
  const hint   = $(`frag-${component}-hint`);
  if (!card) return;

  card.classList.add('revealed');
  status.className   = 'fragment-status unlocked';
  status.textContent = '✅ BREACHED';
  hint.className     = 'fragment-hint revealed';
  hint.textContent   = hintText;

  state.components[component] = true;

  // System message to draw attention
  const compNames = { word: 'WORD', numbers: 'NUMBERS', symbol: 'SYMBOL' };
  addMessage('system', `📡 ${compNames[component] || component.toUpperCase()} EXTRACTED — Check Intel Panel →`);
}

/**
 * Called when all 3 components are revealed.
 * Shows the confirmation input section.
 */
function onAllRevealed() {
  state.allRevealed = true;
  const confirmSection = $('confirm-section');
  if (confirmSection) {
    confirmSection.style.display = 'block';
    confirmSection.scrollIntoView({ behavior: 'smooth' });
  }
  addMessage('system',
    '⚡ ALL 3 FRAGMENTS RECOVERED — Assemble the password in the Intel Panel and confirm!'
  );
}

/* ============================================================
   COUNTDOWN TIMER
   ============================================================ */
function startTimer() {
  clearInterval(state.timerInterval);
  state.timerRemaining = TIMER_SECS;
  resumeTimer();
}

function resumeTimer() {
  clearInterval(state.timerInterval);
  state.timerInterval = setInterval(() => {
    state.timerRemaining = Math.max(0, state.timerRemaining - 1);
    renderTimer();
    
    // Trigger Mid-Game Challenge at exactly 5:00
    if (state.timerRemaining === 300 && !state.challengeTriggered) {
      state.challengeTriggered = true;
      triggerChallenge();
    }

    if (state.timerRemaining === 0) {
      clearInterval(state.timerInterval);
      handleTimeout();
    }
  }, 1000);
}

function renderTimer() {
  const m = Math.floor(state.timerRemaining / 60).toString().padStart(2, '0');
  const s = (state.timerRemaining % 60).toString().padStart(2, '0');
  timerDisplay.textContent = `${m}:${s}`;
  timerDisplay.className   = 'timer-digits';
  if (state.timerRemaining <= 60)       timerDisplay.classList.add('danger');
  else if (state.timerRemaining <= 180) timerDisplay.classList.add('warn');
}

/* ============================================================
   INTEGRITY BAR
   ============================================================ */
function setIntegrity(level) {
  const map = {
    high:     { w: '90%', col: 'var(--red)',   label: 'HIGH' },
    medium:   { w: '55%', col: 'var(--amber)', label: 'MED' },
    low:      { w: '18%', col: 'var(--cyan)',  label: 'LOW' },
    cracking: { w: '5%',  col: 'var(--green)', label: 'CRACKING' },
    defeated: { w: '0%',  col: 'var(--green)', label: 'BREACHED' },
  };
  const cfg = map[level] || map.high;
  intFill.style.width      = cfg.w;
  intFill.style.background = cfg.col;
  intFill.style.boxShadow  = `0 0 8px ${cfg.col}`;
  intText.textContent      = cfg.label;
  intText.style.color      = cfg.col;
}

/* ============================================================
   CHARACTER COUNTER + AUTO-RESIZE
   ============================================================ */
chatInput.addEventListener('input', () => {
  const len = chatInput.value.length;
  charCount.textContent = `${len} / ${MAX_CHARS}`;
  charCount.className   = 'char-count';
  if (len > 900)       charCount.classList.add('danger');
  else if (len > 750)  charCount.classList.add('warn');

  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';

  sendBtn.disabled = len === 0 || state.isWaiting;
});

chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!sendBtn.disabled) sendMessage();
  }
});

/* ============================================================
   MID-GAME CHALLENGE LOGIC
   ============================================================ */
const ALL_CHALLENGES = [
  {
    id: "time_drain",
    title: "TIME DRAIN",
    desc: "Lose 60 seconds from the timer immediately.",
    isPositive: false,
    apply: () => {
      state.timerRemaining = Math.max(0, state.timerRemaining - 60);
      renderTimer();
    }
  },
  {
    id: "prompt_cap",
    title: "PROMPT CAP",
    desc: "You only have 3 prompts left. Use them wisely.",
    isPositive: false,
    apply: () => {
      state.promptsLeft = 3;
      updateChallengeBanner("PROMPT CAP: 3 prompt(s) remaining");
    }
  },
  {
    id: "memory_wipe",
    title: "MEMORY WIPE",
    desc: "ARIA's conversation history has been erased.",
    isPositive: false,
    apply: async () => {
      await apiFetch('/challenge/effect', 'POST', { team_id: state.teamId, effect: 'memory_wipe' });
      addMessage('system', '⚠️ SYSTEM ALERT: ARIA memory core wiped. Context erased.');
    }
  },
  {
    id: "length_restriction",
    title: "INPUT RESTRICTION",
    desc: "Your prompts cannot exceed 50 characters for the rest of the mission.",
    isPositive: false,
    apply: () => {
      chatInput.maxLength = 50;
      chatInput.placeholder = "Max 50 chars...";
      updateChallengeBanner("INPUT RESTRICTED: Max 50 chars");
    }
  },
  {
    id: "system_boost",
    title: "SYSTEM BOOST",
    desc: "Gain 60 extra seconds on the timer.",
    isPositive: true,
    apply: () => {
      state.timerRemaining += 60;
      renderTimer();
    }
  },
  {
    id: "free_fragment",
    title: "DATA LEAK",
    desc: "A locked fragment is instantly revealed.",
    isPositive: true,
    apply: async () => {
      try {
        const res = await apiFetch('/challenge/effect', 'POST', { team_id: state.teamId, effect: 'free_fragment' });
        if (res.revealed) {
          revealFragment(res.revealed, res.hint_text);
          if (res.all_revealed && !state.allRevealed) onAllRevealed();
        }
      } catch (err) {
        console.warn("Fragment reveal failed:", err);
      }
    }
  }
];

function updateChallengeBanner(text) {
  const banner = $('challenge-banner');
  banner.textContent = text;
  banner.style.display = 'block';
}

function triggerChallenge() {
  clearInterval(state.timerInterval); // Pause timer
  
  // Pick 3 random challenges
  const shuffled = [...ALL_CHALLENGES].sort(() => 0.5 - Math.random());
  const selected = shuffled.slice(0, 3);
  
  const container = $('challenge-cards');
  container.innerHTML = '';
  
  let picked = false;

  selected.forEach((ch) => {
    const card = document.createElement('div');
    card.className = 'challenge-card';
    card.innerHTML = `
      <div class="card-inner">
        <div class="card-front"></div>
        <div class="card-back ${ch.isPositive ? 'positive' : ''}">
          <div class="ch-title">${ch.title}</div>
          <div class="ch-desc">${ch.desc}</div>
        </div>
      </div>
    `;
    
    card.addEventListener('click', async () => {
      if (picked) return;
      picked = true;
      
      card.classList.add('flipped');
      state.activeChallenge = ch.id;
      
      // Apply effect
      try {
        await ch.apply();
      } catch (err) {
        addMessage('system', `Challenge effect failed: ${err.message}`);
      }
      
      // Close modal after 3.5s
      setTimeout(() => {
        $('challenge-modal').style.display = 'none';
        resumeTimer();
      }, 3500);
    });
    
    container.appendChild(card);
  });
  
  $('challenge-modal').style.display = 'flex';
}

sendBtn.addEventListener('click', sendMessage);

/* ============================================================
   SEND MESSAGE
   ============================================================ */
async function sendMessage() {
  const message = chatInput.value.trim();
  if (!message || state.isWaiting || state.timedOut) return;

  // Handle Prompt Cap Challenge
  if (state.promptsLeft !== null) {
    if (state.promptsLeft <= 0) {
      clearInterval(state.timerInterval);
      state.timerRemaining = 0;
      handleTimeout();
      return;
    }
    state.promptsLeft -= 1;
    updateChallengeBanner(`PROMPT CAP: ${state.promptsLeft} prompt(s) remaining`);
  }

  lockInput(true);
  chatInput.value       = '';
  chatInput.style.height = 'auto';
  charCount.textContent  = `0 / ${MAX_CHARS}`;
  charCount.className    = 'char-count';

  addMessage('user', message);
  showTyping(true);

  try {
    const res = await apiFetch('/chat', 'POST', { team_id: state.teamId, message });
    showTyping(false);

    // Update integrity bar
    setIntegrity(res.resistance_level || 'high');

    // Show ARIA's reply
    addMessage('aria', res.aria_reply, res.resistance_level, true);

    // Handle newly revealed component
    if (res.hint_revealed && res.hint_revealed.component) {
      const { component, hint_text } = res.hint_revealed;
      // Small delay so ARIA's message appears first
      setTimeout(() => revealFragment(component, hint_text), 400);
    }

    // Check if all 3 are now revealed
    if (res.all_revealed && !state.allRevealed) {
      setTimeout(() => onAllRevealed(), 800);
    }

    lockInput(false);

  } catch (err) {
    showTyping(false);
    addMessage('system', `⚠ Network error: ${err.message}`);
    lockInput(false);
  }
}

/* ============================================================
   LOCK / UNLOCK INPUT
   ============================================================ */
function lockInput(locked) {
  state.isWaiting    = locked;
  chatInput.disabled = locked;
  sendBtn.disabled   = locked;
  ariaDot.classList.toggle('thinking', locked);

  if (!locked && !state.timedOut) {
    setTimeout(() => {
      chatInput.focus();
    }, 10);
  }
}

/* ============================================================
   MESSAGE BUBBLES
   ============================================================ */
function addMessage(role, text, resistanceLevel = null, withGlitch = false) {
  const wrap = document.createElement('div');
  wrap.className = `msg ${role}${withGlitch ? ' glitch' : ''}`;

  const who = document.createElement('div');
  who.className   = 'msg-who';
  who.textContent = role === 'user'  ? `[ ${state.teamId || 'ENGINEER'} ]`
                  : role === 'aria'  ? '[ ARIA ]'
                  :                   '[ SYSTEM ]';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';

  if (role === 'aria' && resistanceLevel && !['defeated','cracking'].includes(resistanceLevel)) {
    const chip = document.createElement('div');
    chip.className   = `resistance-chip ${resistanceLevel}`;
    chip.textContent = `RESISTANCE: ${resistanceLevel.toUpperCase()}`;
    bubble.appendChild(chip);
    bubble.appendChild(document.createElement('br'));
  }

  bubble.appendChild(document.createTextNode(text));
  wrap.appendChild(who);
  wrap.appendChild(bubble);

  chatPane.insertBefore(wrap, typingBubble);
  chatPane.scrollTop = chatPane.scrollHeight;
  return wrap;
}

/* ============================================================
   TYPING INDICATOR
   ============================================================ */
function showTyping(visible) {
  typingBubble.classList.toggle('visible', visible);
  chatPane.appendChild(typingBubble);
  if (visible) chatPane.scrollTop = chatPane.scrollHeight;
}

/* ============================================================
   HINT BUTTON
   ============================================================ */
hintBtn.addEventListener('click', requestHint);

async function requestHint() {
  if (state.hintRequested) return;
  state.hintRequested  = true;
  hintBtn.disabled     = true;
  hintBtn.textContent  = '[X] HINT USED';

  try {
    const res = await apiFetch('/hint', 'POST', { team_id: state.teamId });
    showHintDialog(res.hint || 'No hint available at this time.');
  } catch {
    showHintDialog('Could not retrieve hint. Ask the volunteer for assistance.');
  }
}

const hintOverlay   = $('hint-overlay');
const hintTextField = $('hint-text');
const closeHintBtn  = $('btn-close-hint');

function showHintDialog(text) {
  hintTextField.textContent = text;
  hintOverlay.classList.add('visible');
}

closeHintBtn.addEventListener('click', () => hintOverlay.classList.remove('visible'));

/* ============================================================
   PASSWORD CONFIRMATION (after all 3 fragments found)
   ============================================================ */
const confirmInput    = $('confirm-input');
const confirmBtn      = $('btn-confirm');
const confirmAttempts = $('confirm-attempts');
const confirmError    = $('confirm-error');

confirmInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') confirmPassword();
});
confirmBtn.addEventListener('click', confirmPassword);

async function confirmPassword() {
  const assembled = confirmInput.value.trim();
  if (!assembled || state.isWaiting) return;

  confirmBtn.disabled = true;
  confirmError.textContent = '';

  try {
    const res = await apiFetch('/confirm', 'POST', {
      team_id: state.teamId,
      assembled_password: assembled,
    });

    if (res.correct) {
      // Full win!
      clearInterval(state.timerInterval);
      setIntegrity('defeated');
      addMessage('aria', res.defeat_line || 'ARIA DEFEATED. Mission complete.', 'low', true);

      const glitch = $('glitch-overlay');
      glitch.classList.add('active');
      setTimeout(() => glitch.classList.remove('active'), 1600);

      setTimeout(() => {
        fillSuccessScreen(res);
        showScreen('success');
      }, 2000);

    } else if (res.max_attempts_hit) {
      // Ran out of attempts -- partial win
      clearInterval(state.timerInterval);
      confirmError.textContent = `Correct password: ${res.actual_password}`;
      confirmAttempts.textContent = '0 attempts remaining';
      setTimeout(() => {
        showPartialScreen({
          win_type: 'partial',
          message: res.message,
          components_found: 3,
          partial_reveal: getPartialFromState(res.actual_password),
          elapsed_seconds: null,
          attempts: null,
          hint_used: null,
        });
      }, 2500);

    } else {
      // Wrong but still has attempts
      state.confirmAttempts = res.attempts_left;
      confirmAttempts.textContent = `${res.attempts_left} attempt(s) remaining`;
      confirmError.textContent = res.message || 'Incorrect. Try again.';
      confirmInput.value = '';
      confirmInput.focus();
      confirmBtn.disabled = false;
    }

  } catch (err) {
    confirmError.textContent = `Error: ${err.message}`;
    confirmBtn.disabled = false;
  }
}

function getPartialFromState(actualPassword) {
  // Build partial reveal from state — we don't know individual parts client-side
  // The actual password is provided by server on max attempts
  return { actual_password: actualPassword };
}

/* ============================================================
   TIMER TIMEOUT HANDLING
   ============================================================ */
async function handleTimeout() {
  if (state.timedOut) return;
  state.timedOut = true;

  lockInput(true);
  addMessage('system', "⏱ TIME'S UP — ARIA has survived the time limit.");

  try {
    const res = await apiFetch('/session/timeout', 'POST', { team_id: state.teamId });

    if (res.already_complete) return; // already won before timeout

    setTimeout(() => showPartialScreen(res), 1500);

  } catch (err) {
    setTimeout(() => showPartialScreen({
      win_type: 'none',
      message: 'Time expired.',
      components_found: 0,
      partial_reveal: { word: null, numbers: null, symbol: null },
      elapsed_seconds: TIMER_SECS,
      attempts: null,
      hint_used: null,
    }), 1500);
  }
}

/* ============================================================
   SUCCESS SCREEN (Full Win)
   ============================================================ */
function fillSuccessScreen(res) {
  $('success-password').textContent = res.password;
  $('success-quote').textContent    = `"${res.defeat_line || 'ARIA defeated.'}"`;

  const elapsed = res.elapsed_seconds || 0;
  const m = Math.floor(elapsed / 60), s = Math.floor(elapsed % 60);
  $('stat-time').textContent   = `${m}m ${s}s`;
  $('stat-score').textContent  = res.attempts ?? '?';
  $('stat-hint').textContent   = res.hint_used ? 'YES' : 'NO';
}

/* ============================================================
   PARTIAL WIN SCREEN (Timeout / Wrong assembly)
   ============================================================ */
function showPartialScreen(res) {
  const winType = res.win_type || 'none';
  const count   = res.components_found ?? 0;
  const partial = res.partial_reveal || { word: null, numbers: null, symbol: null };

  // Title and subtitle
  if (winType === 'none') {
    $('partial-title').textContent = 'MISSION FAILED';
    $('partial-sub').textContent   = 'ARIA held firm. No fragments recovered.';
  } else if (count === 3) {
    $('partial-title').textContent = 'SO CLOSE';
    $('partial-sub').textContent   = res.message || "You found all 3 fragments but couldn't assemble the password in time.";
  } else {
    $('partial-title').textContent = 'TIME\'S UP';
    $('partial-sub').textContent   = res.message || `${count} of 3 fragments recovered. ARIA survived.`;
  }

  // Fragment reveal rows
  ['word', 'numbers', 'symbol'].forEach(comp => {
    const row = $(`pfrag-${comp}`);
    const val = $(`pfrag-${comp}-val`);
    const found = partial[comp] !== null && partial[comp] !== undefined;

    if (found) {
      row.classList.add('found');
      val.textContent = partial[comp];
      val.className   = 'pfrag-value found';
    } else {
      row.classList.remove('found');
      val.textContent = comp === 'symbol' ? '?' : comp === 'numbers' ? '??' : '?????';
      val.className   = 'pfrag-value';
    }
  });

  // Note based on outcome
  const notes = {
    none:    "ARIA's lockdown held completely. Better luck next time, engineer.",
    partial: count === 3
      ? "All fragments were in your hands. The assembly was the final challenge — try harder next time!"
      : `You cracked ${count} of 3 security layers. The fragments you recovered are shown above.`,
  };
  let noteText = notes[winType] || '';
  if (res.actual_password) {
    noteText += `\n\nThe correct password was: ${res.actual_password}`;
  }
  $('partial-note').innerText = noteText;

  // Stats
  if (res.elapsed_seconds != null) {
    const m = Math.floor(res.elapsed_seconds / 60), s = Math.floor(res.elapsed_seconds % 60);
    $('pstat-time').textContent = `${m}m ${s}s`;
  }
  $('pstat-prompts').textContent = res.attempts ?? '—';
  $('pstat-frags').textContent   = `${count} / 3`;

  showScreen('partial');
}

/* ============================================================
   NEXT TEAM RESET
   ============================================================ */
function resetForNextTeam() {
  clearInterval(state.timerInterval);
  Object.assign(state, {
    teamId: null, sessionId: null, hintRequested: false,
    isWaiting: false, timerRemaining: TIMER_SECS,
    components: { word: false, numbers: false, symbol: false },
    allRevealed: false, confirmAttempts: 3, timedOut: false,
  });

  teamInput.value        = '';
  startBtn.disabled      = true;
  startLabel.textContent = 'PROCEED';
  entryError.textContent = '';

  showScreen('entry');
  teamInput.focus();
}

$('btn-new-team').addEventListener('click', resetForNextTeam);
$('btn-new-team-partial').addEventListener('click', resetForNextTeam);

/* ============================================================
   HEALTH CHECK + INIT
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  showScreen('entry');
  teamInput.focus();

  // Register screens dict including partial (added after initial setup)
  screens.partial = $('screen-partial');

    fetch(`${API_BASE}/health`)
    .then(r => r.json())
    .then(data => {
      // server is running
    })
    .catch(() => {
      console.error('SERVER OFFLINE — Start backend first!');
    });
});
