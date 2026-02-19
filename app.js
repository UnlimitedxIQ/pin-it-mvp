const realProblems = Array.isArray(window.redditProblems) ? window.redditProblems : [];

const page = document.body.dataset.page || "home";

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function safeUrl(value) {
  try {
    const url = new URL(String(value || ""));
    if (url.protocol === "http:" || url.protocol === "https:") return url.toString();
  } catch (_) {
    // fall through
  }
  return "#";
}

function formatDateFromUnix(unixSeconds) {
  if (!unixSeconds) return "";
  const date = new Date(Number(unixSeconds) * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString();
}

function formatDateFromMs(ms) {
  if (!ms) return "";
  const date = new Date(Number(ms));
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString();
}

function getProblemById(id) {
  return problems.find((item) => item.id === id);
}

const DEMO_MIN_PROBLEM_CARDS = 50;
const DEMO_SECTORS = [
  "SaaS",
  "Commerce",
  "FinTech",
  "HealthTech",
  "PropTech",
  "Business",
  "Mobility",
  "Creator Economy",
];

const DEMO_TITLES = [
  "Customer Onboarding Drop-Off",
  "High Chargeback Disputes",
  "Manual Invoice Reconciliation",
  "Field Scheduling Delays",
  "Inventory Forecast Gaps",
  "Subscription Churn Visibility",
  "Inconsistent Lead Qualification",
  "Order Return Abuse Detection",
  "Employee Training Completion Gaps",
  "Freelancer Payment Delays",
  "Support Ticket SLA Misses",
  "Low Conversion on Trial Users",
  "Supplier Communication Breakdowns",
  "Document Compliance Tracking",
  "Ad Spend Attribution Gaps",
  "B2B Proposal Follow-Up Delays",
  "Recruiting Pipeline Bottlenecks",
  "Appointment No-Show Rates",
];

const DEMO_COMPLAINT_SNIPPETS = [
  "Teams are still handling this manually and it causes repeated delays each week.",
  "Current tools do not integrate well, so data is fragmented across multiple places.",
  "Stakeholders report missed deadlines because ownership is unclear between teams.",
  "Customers are frustrated by inconsistent updates and limited self-serve visibility.",
  "The process breaks during peak demand and escalations become frequent.",
  "Existing software is expensive and still does not solve the core workflow bottleneck.",
  "People keep creating spreadsheet workarounds that introduce errors and rework.",
  "The issue affects revenue, retention, and response time for critical requests.",
];

const DEMO_TEAM_BLUEPRINTS = [
  {
    title: "Workflow Automation Layer",
    summary: "Build a lightweight automation workflow to remove repetitive manual steps and reduce turnaround time.",
    roles: ["Full-Stack Engineer", "Product Manager", "Operations Lead"],
  },
  {
    title: "Data Visibility Dashboard",
    summary: "Launch a shared dashboard with live metrics so teams can catch bottlenecks early and coordinate action.",
    roles: ["Backend Engineer", "Data/AI Engineer", "Designer"],
  },
  {
    title: "Customer Feedback Triage System",
    summary: "Standardize incoming issue triage and priority scoring so the highest impact problems are resolved first.",
    roles: ["Product Manager", "Growth Marketer", "Operations Lead"],
  },
  {
    title: "Compliance and QA Assistant",
    summary: "Create policy checks and QA prompts to reduce risk while maintaining delivery speed.",
    roles: ["Finance/Compliance", "Backend Engineer", "Product Manager"],
  },
];

function buildDemoComplaints(problemTitle, sector, seed) {
  const now = Math.floor(Date.now() / 1000);
  const complaints = [];
  for (let i = 0; i < 5; i += 1) {
    const snippet = DEMO_COMPLAINT_SNIPPETS[(seed + i) % DEMO_COMPLAINT_SNIPPETS.length];
    complaints.push({
      text: `${problemTitle}: ${snippet}`,
      subreddit: `${String(sector || "business").toLowerCase().replace(/\s+/g, "")}_demo`,
      author: `demo_user_${seed + i + 1}`,
      score: 8 + ((seed + i) % 30),
      createdUtc: now - (seed + i) * 3700,
      postTitle: `${problemTitle} discussion thread`,
      sourceUrl: "#",
    });
  }
  return complaints;
}

function buildDemoTeams(problemId, problemTitle, seed) {
  const now = Date.now();
  return [0, 1].map((offset) => {
    const blueprint = DEMO_TEAM_BLUEPRINTS[(seed + offset) % DEMO_TEAM_BLUEPRINTS.length];
    const teamNum = offset + 1;
    return {
      id: `${problemId}-demo-team-${teamNum}`,
      solutionTitle: blueprint.title,
      summary: blueprint.summary,
      roles: blueprint.roles,
      ownerName: `Demo Founder ${teamNum}`,
      ownerEmail: `founder${teamNum}@pinit.demo`,
      members: [
        {
          name: `Demo Founder ${teamNum}`,
          email: `founder${teamNum}@pinit.demo`,
          joinedAt: now - (offset * 2000),
        },
      ],
      createdAt: now - (offset * 5000),
    };
  });
}

function enrichProblemForDemo(problem, seed) {
  const baseTitle = String(problem.title || "Untitled Issue");
  const baseSector = String(problem.sector || DEMO_SECTORS[seed % DEMO_SECTORS.length]);
  const existingComplaints = Array.isArray(problem.complaints) ? problem.complaints : [];
  const supplementalComplaints = buildDemoComplaints(baseTitle, baseSector, seed);
  const complaintPayload = [...existingComplaints, ...supplementalComplaints].slice(0, 220);
  const complaintCount = Math.max(5, Number(problem.complaintCount || 0), complaintPayload.length);
  const demoTeams = buildDemoTeams(String(problem.id), baseTitle, seed);
  const existingDemoTeams = Array.isArray(problem.demoTeams) ? problem.demoTeams : [];

  return {
    ...problem,
    sector: baseSector,
    sourcePlatform: problem.sourcePlatform || "Demo",
    sourceSubreddits: Array.isArray(problem.sourceSubreddits) ? problem.sourceSubreddits : [],
    complaints: complaintPayload,
    complaintCount,
    teams: Math.max(2, Number(problem.teams || 0)),
    demoTeams: [...existingDemoTeams, ...demoTeams],
  };
}

function createDemoProblems(existingProblems, minimumCards) {
  const existingIds = new Set(existingProblems.map((problem) => String(problem.id)));
  const fillCount = Math.max(0, minimumCards - existingProblems.length);
  const fillers = [];

  for (let index = 0; index < fillCount; index += 1) {
    const title = DEMO_TITLES[index % DEMO_TITLES.length];
    const sector = DEMO_SECTORS[index % DEMO_SECTORS.length];
    const id = `demo-issue-${index + 1}`;
    if (existingIds.has(id)) continue;

    fillers.push({
      id,
      title,
      sector,
      summary: `Demo issue card for MVP presentation in ${sector}.`,
      interested: 40 + ((index * 13) % 170),
      teams: 2,
      demand: index % 3 === 0 ? "high" : (index % 3 === 1 ? "medium" : "low"),
      fresh: index % 2 === 0,
      investor: index % 4 === 0,
      complaintCount: 5 + (index % 7),
      sourcePlatform: "Demo",
      sourceSubreddits: [],
      complaints: [],
      solutions: [],
      status: "demo",
    });
  }

  return fillers;
}

const problems = [
  ...realProblems,
  ...createDemoProblems(realProblems, DEMO_MIN_PROBLEM_CARDS),
]
  .slice(0, DEMO_MIN_PROBLEM_CARDS)
  .map((problem, index) => enrichProblemForDemo(problem, index));

const sectorVisuals = {
  EdTech: { icon: "🎓", top: "#6078ea", bottom: "#17ead9" },
  HealthTech: { icon: "🩺", top: "#2bc0e4", bottom: "#eaecc6" },
  "Food Ops": { icon: "🍽️", top: "#f2994a", bottom: "#f2c94c" },
  "Creator Economy": { icon: "🎬", top: "#9d50bb", bottom: "#6e48aa" },
  PropTech: { icon: "🏢", top: "#56ab2f", bottom: "#a8e063" },
  Commerce: { icon: "🛍️", top: "#ff9966", bottom: "#ff5e62" },
  FinTech: { icon: "💳", top: "#1d4350", bottom: "#a43931" },
  "Family Mobility": { icon: "🚌", top: "#3a7bd5", bottom: "#3a6073" },
  Mobility: { icon: "🚆", top: "#11998e", bottom: "#38ef7d" },
  Business: { icon: "📈", top: "#6441a5", bottom: "#2a0845" },
  Career: { icon: "💼", top: "#8360c3", bottom: "#2ebf91" },
  SaaS: { icon: "☁️", top: "#396afc", bottom: "#2948ff" },
};

function buildSectorBackground(sector) {
  const visual = sectorVisuals[sector] || { icon: "💡", top: "#5f72bd", bottom: "#9b23ea" };
  const label = String(sector || "Issue").toUpperCase();
  const svg = `
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 800'>
      <defs>
        <linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
          <stop offset='0%' stop-color='${visual.top}' />
          <stop offset='100%' stop-color='${visual.bottom}' />
        </linearGradient>
      </defs>
      <rect width='1200' height='800' fill='url(#g)' />
      <circle cx='980' cy='130' r='200' fill='rgba(255,255,255,0.14)' />
      <circle cx='230' cy='690' r='240' fill='rgba(255,255,255,0.12)' />
      <text x='600' y='350' font-size='190' text-anchor='middle' dominant-baseline='middle'>${visual.icon}</text>
      <text x='600' y='690' font-size='70' text-anchor='middle' fill='rgba(255,255,255,0.92)' font-family='Segoe UI,Arial,sans-serif' font-weight='700'>${label}</text>
    </svg>
  `;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}

const USER_TEAM_STORAGE_KEY = "pinItUserTeams";
const INTERESTED_STORAGE_KEY = "pinItInterestedProblems";
const TEAM_MESSAGES_STORAGE_KEY = "pinItTeamMessages";
const USER_PROFILE_STORAGE_KEY = "pinItUserProfile";
const HOME_SELECTED_PROBLEM_KEY = "pinItHomeSelectedProblem";

function storageAvailable() {
  try {
    return typeof window !== "undefined" && Boolean(window.localStorage);
  } catch (_) {
    return false;
  }
}

function loadStorageObject(key, fallback = {}) {
  if (!storageAvailable()) return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : fallback;
    if (parsed && typeof parsed === "object") return parsed;
  } catch (_) {
    // fall through
  }
  return fallback;
}

function saveStorageObject(key, value) {
  if (!storageAvailable()) return;
  window.localStorage.setItem(key, JSON.stringify(value));
}

function loadUserTeamMap() {
  return loadStorageObject(USER_TEAM_STORAGE_KEY, {});
}

function saveUserTeamMap(map) {
  saveStorageObject(USER_TEAM_STORAGE_KEY, map);
}

function sanitizeEmail(value) {
  const email = String(value || "").trim();
  if (!email) return "";
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? email : "";
}

function loadInterestedProblemIds() {
  const raw = loadStorageObject(INTERESTED_STORAGE_KEY, []);
  if (!Array.isArray(raw)) return new Set();
  return new Set(raw.map((id) => String(id)));
}

function saveInterestedProblemIds(ids) {
  saveStorageObject(INTERESTED_STORAGE_KEY, Array.from(ids));
}

function setInterested(problemId, active) {
  const ids = loadInterestedProblemIds();
  const key = String(problemId);
  if (active) ids.add(key);
  else ids.delete(key);
  saveInterestedProblemIds(ids);
}

function isInterested(problemId) {
  const ids = loadInterestedProblemIds();
  return ids.has(String(problemId));
}

function loadTeamMessageMap() {
  return loadStorageObject(TEAM_MESSAGES_STORAGE_KEY, {});
}

function saveTeamMessageMap(map) {
  saveStorageObject(TEAM_MESSAGES_STORAGE_KEY, map);
}

function getMessagesForTeam(teamId, map) {
  const sourceMap = map && typeof map === "object" ? map : loadTeamMessageMap();
  const messages = Array.isArray(sourceMap[teamId]) ? sourceMap[teamId] : [];
  return messages
    .map((message) => ({
      senderName: String(message?.senderName || "Community member"),
      senderEmail: sanitizeEmail(message?.senderEmail || ""),
      message: String(message?.message || "").trim(),
      createdAt: Number(message?.createdAt || Date.now()),
      problemId: String(message?.problemId || ""),
      teamTitle: String(message?.teamTitle || ""),
    }))
    .filter((message) => message.message)
    .sort((a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0));
}

function addMessageToTeam(teamId, payload) {
  const map = loadTeamMessageMap();
  const teamMessages = getMessagesForTeam(teamId, map);
  teamMessages.unshift({
    senderName: String(payload?.senderName || "Community member"),
    senderEmail: sanitizeEmail(payload?.senderEmail || ""),
    message: String(payload?.message || ""),
    createdAt: Number(payload?.createdAt || Date.now()),
    problemId: String(payload?.problemId || ""),
    teamTitle: String(payload?.teamTitle || ""),
  });
  map[teamId] = teamMessages;
  saveTeamMessageMap(map);
}

function loadCurrentUser() {
  const profile = loadStorageObject(USER_PROFILE_STORAGE_KEY, {});
  return {
    name: String(profile?.name || "").trim(),
    email: sanitizeEmail(profile?.email || ""),
  };
}

function saveCurrentUser(name, email) {
  const safeName = String(name || "").trim();
  const safeEmail = sanitizeEmail(email || "");
  if (!safeName && !safeEmail) return;
  saveStorageObject(USER_PROFILE_STORAGE_KEY, { name: safeName, email: safeEmail });
}

function getStoredHomeSelectedProblemId() {
  if (!storageAvailable()) return "";
  return String(window.localStorage.getItem(HOME_SELECTED_PROBLEM_KEY) || "").trim();
}

function setStoredHomeSelectedProblemId(problemId) {
  if (!storageAvailable()) return;
  window.localStorage.setItem(HOME_SELECTED_PROBLEM_KEY, String(problemId || ""));
}

function normalizeMember(member) {
  const name = String(member?.name || "").trim();
  const email = sanitizeEmail(member?.email || "");
  return {
    name: name || "Community member",
    email,
    joinedAt: Number(member?.joinedAt || Date.now()),
    joinedByCurrentUser: Boolean(member?.joinedByCurrentUser),
  };
}

function normalizeTeam(problemId, team, fallbackIndex) {
  const ownerName = String(team?.ownerName || team?.proposer || "Community Member").trim();
  const ownerEmail = sanitizeEmail(team?.ownerEmail || "");
  const members = Array.isArray(team?.members)
    ? team.members.map(normalizeMember).filter((member) => member.name)
    : [];

  if (members.length === 0) {
    members.push({ name: ownerName || "Community Member", email: ownerEmail, joinedAt: Date.now() });
  }

  return {
    id: String(team?.id || `${problemId}-team-${fallbackIndex}`),
    problemId: String(problemId),
    solutionTitle: String(team?.solutionTitle || team?.title || "Untitled Proposal").trim(),
    summary: String(team?.summary || "").trim() || "No summary provided.",
    roles: Array.isArray(team?.roles) ? team.roles.map((role) => String(role || "").trim()).filter(Boolean).slice(0, 8) : [],
    ownerName: ownerName || "Community Member",
    ownerEmail,
    members,
    createdAt: Number(team?.createdAt || Date.now()),
    ownedByCurrentUser: Boolean(team?.ownedByCurrentUser),
    joinedByCurrentUser: Boolean(team?.joinedByCurrentUser),
  };
}

function getSeededTeamsForProblem(problemId) {
  const problem = getProblemById(problemId);
  const teams = Array.isArray(problem?.demoTeams) ? problem.demoTeams : [];
  return teams.map((team, index) => normalizeTeam(problemId, team, index + 500));
}

function getTeamsForProblem(problemId, map, includeSeed = true) {
  const sourceMap = map && typeof map === "object" ? map : loadUserTeamMap();
  const userTeams = (Array.isArray(sourceMap[problemId]) ? sourceMap[problemId] : [])
    .map((team, index) => normalizeTeam(problemId, team, index + 1));
  const seededTeams = includeSeed ? getSeededTeamsForProblem(problemId) : [];

  const seen = new Set();
  return [...userTeams, ...seededTeams]
    .filter((team) => {
      if (seen.has(team.id)) return false;
      seen.add(team.id);
      return true;
    })
    .sort((a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0));
}

function getUserTeamsForProblem(problemId, map) {
  const sourceMap = map && typeof map === "object" ? map : loadUserTeamMap();
  return (Array.isArray(sourceMap[problemId]) ? sourceMap[problemId] : [])
    .map((team, index) => normalizeTeam(problemId, team, index + 1))
    .sort((a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0));
}

function saveTeamsForProblem(problemId, teams, map) {
  const sourceMap = map && typeof map === "object" ? map : loadUserTeamMap();
  sourceMap[problemId] = Array.isArray(teams) ? teams : [];
  saveUserTeamMap(sourceMap);
}

function getTeamCountForProblem(problem, map) {
  if (!problem?.id) return 0;
  const userCount = getTeamsForProblem(problem.id, map).length;
  const seededCount = Math.max(0, Number(problem.teams || 0));
  return Math.max(userCount, seededCount);
}

function renderHomeDashboard() {
  const listEl = document.getElementById("homeProblemList");
  const detailEl = document.getElementById("homeDetail");
  const countsEl = document.getElementById("homeCounts");
  if (!listEl || !detailEl) return;

  const searchInput = document.getElementById("searchInput");
  let searchTerm = "";
  let selectedProblemId = getStoredHomeSelectedProblemId();

  function getInterestedProblems() {
    const interested = loadInterestedProblemIds();
    return problems.filter((problem) => interested.has(String(problem.id)));
  }

  function getOwnedTeams(problemId) {
    return getTeamsForProblem(problemId).filter((team) => team.ownedByCurrentUser);
  }

  function getJoinedTeams(problemId) {
    return getTeamsForProblem(problemId).filter((team) => team.joinedByCurrentUser && !team.ownedByCurrentUser);
  }

  function renderDetail(problem) {
    if (!problem) {
      detailEl.innerHTML = `
        <div class="empty-state">
          Click "I'm Interested" on Discover cards to build your home dashboard.
        </div>
      `;
      return;
    }

    const allTeams = getTeamsForProblem(problem.id);
    const ownedTeams = getOwnedTeams(problem.id);
    const joinedTeams = getJoinedTeams(problem.id);
    const ownedTeamsAll = problems.flatMap((item) => getOwnedTeams(item.id).map((team) => ({ ...team, problemTitle: item.title })));
    const joinedTeamsAll = problems.flatMap((item) => getJoinedTeams(item.id).map((team) => ({ ...team, problemTitle: item.title })));
    const complaints = Array.isArray(problem.complaints) ? problem.complaints.slice(0, 6) : [];

    const ownedTeamIds = new Set(ownedTeams.map((team) => team.id));
    const inboxMessages = ownedTeamsAll
      .flatMap((team) => getMessagesForTeam(team.id).map((message) => ({ ...message, teamId: team.id, problemTitle: team.problemTitle || "" })))
      .sort((a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0));

    const complaintMarkup = complaints.length > 0
      ? complaints.map((complaint) => `<li>${escapeHtml(complaint.text || "")}</li>`).join("")
      : "<li>No complaint details yet.</li>";

    const teamMarkup = allTeams.length > 0
      ? allTeams.map((team) => {
        const members = Array.isArray(team.members) ? team.members.map((member) => escapeHtml(member.name)).join(", ") : "";
        const label = ownedTeamIds.has(team.id)
          ? "Your team"
          : (team.joinedByCurrentUser ? "You joined" : "Open team");
        return `
          <article class="home-team-item">
            <div class="home-team-head">
              <h4>${escapeHtml(team.solutionTitle)}</h4>
              <span class="team-tag">${label}</span>
            </div>
            <p>${escapeHtml(team.summary)}</p>
            <p class="home-small">Members: ${escapeHtml(members || "No members yet")}</p>
          </article>
        `;
      }).join("")
      : `<div class="empty-state">No teams available yet for this problem.</div>`;

    const ownedMarkup = ownedTeamsAll.length > 0
      ? ownedTeamsAll.map((team) => `<li>${escapeHtml(team.solutionTitle)} • ${escapeHtml(team.problemTitle || "Unknown problem")} (${team.members.length} members)</li>`).join("")
      : "<li>No proposed teams yet.</li>";

    const joinedMarkup = joinedTeamsAll.length > 0
      ? joinedTeamsAll.map((team) => `<li>${escapeHtml(team.solutionTitle)} • ${escapeHtml(team.problemTitle || "Unknown problem")} (${team.members.length} members)</li>`).join("")
      : "<li>No joined teams yet.</li>";

    const inboxMarkup = inboxMessages.length > 0
      ? inboxMessages.map((message) => `
        <article class="home-message-item">
          <p><strong>${escapeHtml(message.senderName)}</strong> on ${escapeHtml(message.teamTitle || "your team")}</p>
          <p>${escapeHtml(message.message)}</p>
          <p class="home-small">${escapeHtml(message.problemTitle || "General")} • ${escapeHtml(formatDateFromMs(message.createdAt))}${message.senderEmail ? ` • ${escapeHtml(message.senderEmail)}` : ""}</p>
        </article>
      `).join("")
      : `<div class="empty-state">No messages yet for your solution teams.</div>`;

    detailEl.innerHTML = `
      <section class="home-detail-card">
        <h2>${escapeHtml(problem.title)}</h2>
        <div class="detail-tag-row">
          <span class="team-tag">${escapeHtml(problem.sector)}</span>
          <span class="team-tag">${Number(problem.complaintCount || 0)} complaints</span>
          <span class="team-tag">${allTeams.length} current teams</span>
        </div>
        <p>${escapeHtml(problem.summary || "No summary available.")}</p>
      </section>

      <section class="home-detail-card">
        <h3>Current Solutions</h3>
        <div class="home-team-list">${teamMarkup}</div>
      </section>

      <section class="home-detail-split">
        <article class="home-detail-card">
          <h3>Your Proposed Solutions</h3>
          <ul class="home-list">${ownedMarkup}</ul>
        </article>
        <article class="home-detail-card">
          <h3>Solutions You Joined</h3>
          <ul class="home-list">${joinedMarkup}</ul>
        </article>
      </section>

      <section class="home-detail-card">
        <h3>Complaint Evidence</h3>
        <ul class="home-list">${complaintMarkup}</ul>
      </section>

      <section class="home-detail-card">
        <h3>Team Messages</h3>
        <div class="home-message-list">${inboxMarkup}</div>
      </section>
    `;
  }

  function renderList() {
    const interestedProblems = getInterestedProblems();
    const filtered = interestedProblems.filter((problem) => {
      if (!searchTerm) return true;
      return `${problem.title} ${problem.sector}`.toLowerCase().includes(searchTerm);
    });

    if (!filtered.some((problem) => String(problem.id) === String(selectedProblemId))) {
      selectedProblemId = filtered.length > 0 ? String(filtered[0].id) : "";
      setStoredHomeSelectedProblemId(selectedProblemId);
    }

    if (countsEl) {
      const ownedCount = interestedProblems.reduce((sum, problem) => sum + getOwnedTeams(problem.id).length, 0);
      const joinedCount = interestedProblems.reduce((sum, problem) => sum + getJoinedTeams(problem.id).length, 0);
      countsEl.textContent = `${interestedProblems.length} interested • ${ownedCount} proposed • ${joinedCount} joined`;
    }

    if (filtered.length === 0) {
      listEl.innerHTML = `<div class="empty-state">No interested problems match your search.</div>`;
      renderDetail(null);
      return;
    }

    listEl.innerHTML = "";
    filtered.forEach((problem) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `home-problem-card ${String(problem.id) === String(selectedProblemId) ? "active" : ""}`;
      button.style.backgroundImage = buildSectorBackground(problem.sector);
      button.innerHTML = `
        <strong>${escapeHtml(problem.title)}</strong>
        <span>${escapeHtml(problem.sector)}</span>
        <span>${Number(problem.complaintCount || 0)} complaints</span>
      `;
      button.addEventListener("click", () => {
        selectedProblemId = String(problem.id);
        setStoredHomeSelectedProblemId(selectedProblemId);
        renderList();
      });
      listEl.appendChild(button);
    });

    renderDetail(getProblemById(selectedProblemId));
  }

  if (searchInput) {
    searchInput.placeholder = "Search your interested problems...";
    searchInput.addEventListener("input", (event) => {
      searchTerm = event.target.value.trim().toLowerCase();
      renderList();
    });
  }

  renderList();
}

function initFeedPage() {
  if (page === "home") {
    renderHomeDashboard();
    return;
  }

  const feedEl = document.getElementById("pinFeed");
  const template = document.getElementById("cardTemplate");
  if (!feedEl || !template) return;

  const searchInput = document.getElementById("searchInput");
  const sectorFilters = document.getElementById("sectorFilters");
  const chips = Array.from(document.querySelectorAll(".chip"));

  const problemCountEl = document.getElementById("problemCount");
  const interestCountEl = document.getElementById("interestCount");
  const teamCountEl = document.getElementById("teamCount");

  const state = {
    activeSector: "All",
    activeChip: document.body.dataset.defaultChip || "all",
    searchTerm: "",
  };

  function getSectors() {
    return ["All", ...new Set(problems.map((p) => p.sector).filter(Boolean))];
  }

  function renderSectorButtons() {
    if (!sectorFilters) return;
    sectorFilters.innerHTML = "";

    getSectors().forEach((sector) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `sector-btn ${sector === state.activeSector ? "active" : ""}`;
      button.textContent = sector;
      button.addEventListener("click", () => {
        state.activeSector = sector;
        renderSectorButtons();
        renderCards();
      });
      sectorFilters.appendChild(button);
    });
  }

  function matchesChip(problem) {
    if (state.activeChip === "all") return true;
    if (state.activeChip === "high") return problem.demand === "high";
    if (state.activeChip === "new") return Boolean(problem.fresh);
    if (state.activeChip === "funding") return Boolean(problem.investor);
    return true;
  }

  function matchesSearch(problem) {
    if (!state.searchTerm) return true;
    const haystack = `${problem.title} ${problem.summary} ${problem.sector}`.toLowerCase();
    return haystack.includes(state.searchTerm);
  }

  function filteredProblems() {
    return problems.filter((problem) => {
      const bySector = state.activeSector === "All" || problem.sector === state.activeSector;
      return bySector && matchesChip(problem) && matchesSearch(problem);
    });
  }

  function updatePulse(currentList, teamMap) {
    if (!problemCountEl || !interestCountEl || !teamCountEl) return;
    const totalInterest = currentList.reduce((sum, p) => sum + Number(p.interested || 0), 0);
    const totalTeams = currentList.reduce((sum, p) => sum + getTeamCountForProblem(p, teamMap), 0);

    problemCountEl.textContent = currentList.length;
    interestCountEl.textContent = totalInterest;
    teamCountEl.textContent = totalTeams;
  }

  function renderCards() {
    feedEl.innerHTML = "";
    const current = filteredProblems();
    const teamMap = loadUserTeamMap();
    const interestedIds = loadInterestedProblemIds();

    if (current.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = problems.length === 0
        ? "No real data loaded yet. Run the Reddit scraper to populate issues."
        : "No matching issues found. Try a broader search or different filters.";
      feedEl.appendChild(empty);
      updatePulse(current, teamMap);
      return;
    }

    current.forEach((problem, index) => {
      const fragment = template.content.cloneNode(true);
      const card = fragment.querySelector(".card");
      const titleLink = fragment.querySelector(".problem-link");
      const meta = fragment.querySelectorAll(".meta-item");
      const interestedBtn = fragment.querySelector(".interested-btn");
      const solutionsLink = fragment.querySelector(".view-solutions-link");
      const teamCount = getTeamCountForProblem(problem, teamMap);

      card.style.backgroundImage = buildSectorBackground(problem.sector);
      titleLink.textContent = String(problem.title || "Untitled Issue");
      titleLink.href = `problem.html?id=${encodeURIComponent(problem.id)}`;

      meta[0].textContent = `${Number(problem.interested || 0)} people interested`;
      meta[1].textContent = `${teamCount} teams forming`;

      solutionsLink.href = `solutions.html?problem=${encodeURIComponent(problem.id)}`;
      interestedBtn.classList.toggle("active", interestedIds.has(String(problem.id)));

      interestedBtn.addEventListener("click", () => {
        const isActive = interestedBtn.classList.toggle("active");
        setInterested(problem.id, isActive);
        const currentInterested = Number(problem.interested || 0);
        problem.interested = Math.max(0, currentInterested + (isActive ? 1 : -1));
        meta[0].textContent = `${problem.interested} people interested`;
        updatePulse(filteredProblems(), loadUserTeamMap());
      });

      card.style.animationDelay = `${index * 45}ms`;
      feedEl.appendChild(fragment);
    });

    updatePulse(current, teamMap);
  }

  chips.forEach((chip) => {
    if (chip.dataset.chip === state.activeChip) {
      chips.forEach((item) => item.classList.remove("active"));
      chip.classList.add("active");
    }

    chip.addEventListener("click", () => {
      chips.forEach((item) => item.classList.remove("active"));
      chip.classList.add("active");
      state.activeChip = chip.dataset.chip;
      renderCards();
    });
  });

  if (searchInput) {
    searchInput.addEventListener("input", (event) => {
      state.searchTerm = event.target.value.trim().toLowerCase();
      renderCards();
    });
  }

  renderSectorButtons();
  renderCards();
}

function renderSolutionsPage() {
  const directoryEl = document.getElementById("problemDirectory");
  const panelEl = document.getElementById("solutionsPanel");
  const solutionsGridEl = document.getElementById("solutionsGrid");
  const formEl = document.getElementById("solutionForm");
  if (!directoryEl || !panelEl || !solutionsGridEl) return;

  const searchInput = document.getElementById("searchInput");
  const contextEl = document.getElementById("solutionsContext");
  const params = new URLSearchParams(window.location.search);
  const selectedProblemId = params.get("problem");
  const selectedProblem = selectedProblemId ? getProblemById(selectedProblemId) : null;
  let searchTerm = "";

  function buildMailto(ownerEmail, solutionTitle) {
    const email = sanitizeEmail(ownerEmail);
    if (!email) return "";
    const subject = encodeURIComponent(`Pin It Team: ${solutionTitle}`);
    return `mailto:${encodeURIComponent(email)}?subject=${subject}`;
  }

  function renderDirectory() {
    const query = searchTerm.trim().toLowerCase();
    const teamMap = loadUserTeamMap();
    const filtered = problems.filter((problem) => {
      if (!query) return true;
      return `${problem.title} ${problem.sector}`.toLowerCase().includes(query);
    });

    directoryEl.innerHTML = "";
    panelEl.classList.add("hidden");

    if (contextEl) {
      contextEl.textContent = "Select a problem to view teams, join one, or start your own.";
    }

    if (filtered.length === 0) {
      directoryEl.innerHTML = `<div class="empty-state">No problems found. Run the scraper to populate real data.</div>`;
      return;
    }

    filtered.forEach((problem) => {
      const complaintCount = Number(problem.complaintCount || 0);
      const teamCount = getTeamCountForProblem(problem, teamMap);
      const article = document.createElement("article");
      article.className = "problem-directory-card";
      article.innerHTML = `
        <h3>${escapeHtml(problem.title)}</h3>
        <p>${escapeHtml(problem.sector)}${complaintCount ? ` • ${complaintCount} complaints` : ""}</p>
        <p>${teamCount} teams forming</p>
        <a class="ghost-btn" href="solutions.html?problem=${encodeURIComponent(problem.id)}">View Solutions</a>
      `;
      directoryEl.appendChild(article);
    });
  }

  function addMemberToTeam(problemId, teamId, name, email) {
    const safeName = String(name || "").trim();
    const safeEmail = sanitizeEmail(email || "");
    if (!safeName) return false;

    const map = loadUserTeamMap();
    const allTeams = getTeamsForProblem(problemId, map, true);
    const sourceTeam = allTeams.find((team) => team.id === teamId);
    if (!sourceTeam) return false;

    const exists = sourceTeam.members.some((member) => {
      const sameName = String(member.name || "").trim().toLowerCase() === safeName.toLowerCase();
      const sameEmail = safeEmail && String(member.email || "").trim().toLowerCase() === safeEmail.toLowerCase();
      return sameName || Boolean(sameEmail);
    });
    if (exists) return false;

    const updatedTeam = {
      ...sourceTeam,
      joinedByCurrentUser: true,
      members: [...sourceTeam.members, {
        name: safeName,
        email: safeEmail,
        joinedAt: Date.now(),
        joinedByCurrentUser: true,
      }],
    };

    const userTeams = getUserTeamsForProblem(problemId, map);
    const userIndex = userTeams.findIndex((team) => team.id === teamId);
    if (userIndex === -1) userTeams.unshift(updatedTeam);
    else userTeams[userIndex] = updatedTeam;
    saveTeamsForProblem(problemId, userTeams, map);
    saveCurrentUser(safeName, safeEmail);
    return true;
  }

  function askAboutTeam(problem, team) {
    const profile = loadCurrentUser();
    const senderNameInput = window.prompt("Your name:", profile.name || "");
    if (senderNameInput === null) return;
    const senderName = senderNameInput.trim();
    if (!senderName) {
      alert("Name is required.");
      return;
    }

    const senderEmailInput = window.prompt("Your email (optional):", profile.email || "") || "";
    const senderEmail = senderEmailInput.trim();
    if (senderEmail && !sanitizeEmail(senderEmail)) {
      alert("Email format looks invalid.");
      return;
    }

    const messageInput = window.prompt("What do you want to ask about this solution?");
    if (messageInput === null) return;
    const message = messageInput.trim();
    if (!message) {
      alert("Please enter a message.");
      return;
    }

    addMessageToTeam(team.id, {
      senderName,
      senderEmail,
      message,
      createdAt: Date.now(),
      problemId: problem.id,
      teamTitle: team.solutionTitle,
    });
    saveCurrentUser(senderName, senderEmail);
    alert("Message sent to the team inbox.");
  }

  function renderSolutionsForProblem(problem) {
    const allTeams = getTeamsForProblem(problem.id);
    const filteredTeams = allTeams.filter((team) => {
      if (!searchTerm) return true;
      const memberNames = team.members.map((member) => member.name).join(" ");
      const haystack = `${team.solutionTitle} ${team.summary} ${team.ownerName} ${(team.roles || []).join(" ")} ${memberNames}`.toLowerCase();
      return haystack.includes(searchTerm);
    });

    directoryEl.innerHTML = "";
    panelEl.classList.remove("hidden");
    solutionsGridEl.innerHTML = "";

    if (contextEl) {
      contextEl.textContent = `Showing solution teams for: ${problem.title}`;
    }

    if (filteredTeams.length === 0) {
      solutionsGridEl.innerHTML = `<div class="empty-state">No teams yet for this problem. Submit a solution to start the first team.</div>`;
      return;
    }

    filteredTeams.forEach((team) => {
      const roles = Array.isArray(team.roles) ? team.roles : [];
      const created = formatDateFromMs(team.createdAt);
      const roleChips = roles.map((role) => `<span class="role-chip">${escapeHtml(role)}</span>`).join("");
      const memberChips = team.members
        .slice(0, 8)
        .map((member) => `<span class="team-tag">${escapeHtml(member.name)}</span>`)
        .join("");
      const mailto = buildMailto(team.ownerEmail, team.solutionTitle);

      const article = document.createElement("article");
      article.className = "solution-card";
      article.innerHTML = `
        <div class="solution-head">
          <h3>${escapeHtml(team.solutionTitle)}</h3>
          <span class="team-tag">${team.ownedByCurrentUser ? "Your Team" : "Team"}</span>
        </div>
        <p class="solution-byline">Owner: ${escapeHtml(team.ownerName)}${created ? ` • ${escapeHtml(created)}` : ""}</p>
        <p>${escapeHtml(team.summary)}</p>
        <div class="roles-row">${roleChips || '<span class="role-chip">Generalist</span>'}</div>
        <div class="team-tag-row">${memberChips || '<span class="team-tag">No members yet</span>'}</div>
        <div class="solution-foot">
          <span>${team.members.length} members</span>
          <span>${escapeHtml(problem.sector)}</span>
        </div>
        <div class="solution-actions">
          <button type="button" class="ghost-btn join-team-btn" data-team-id="${escapeHtml(team.id)}">Join Team</button>
          <button type="button" class="ghost-btn ask-team-btn" data-team-id="${escapeHtml(team.id)}">Ask Question</button>
          ${mailto ? `<a class="ghost-btn" href="${mailto}">Email Owner</a>` : '<span class="team-tag">Email not shared</span>'}
        </div>
      `;

      const joinBtn = article.querySelector(".join-team-btn");
      if (joinBtn) {
        joinBtn.addEventListener("click", () => {
          const profile = loadCurrentUser();
          const joinName = window.prompt("Enter your name to join this team:", profile.name || "");
          if (joinName === null) return;
          const trimmedName = joinName.trim();
          if (!trimmedName) {
            alert("Name is required to join a team.");
            return;
          }

          const joinEmailInput = window.prompt("Enter your email (optional):", profile.email || "") || "";
          const trimmedEmail = joinEmailInput.trim();
          if (trimmedEmail && !sanitizeEmail(trimmedEmail)) {
            alert("Email format looks invalid. Please try again.");
            return;
          }

          const added = addMemberToTeam(problem.id, team.id, trimmedName, trimmedEmail);
          if (!added) {
            alert("You are already on this team or the team is no longer available.");
            return;
          }
          renderSolutionsForProblem(problem);
        });
      }

      const askBtn = article.querySelector(".ask-team-btn");
      if (askBtn) {
        askBtn.addEventListener("click", () => {
          askAboutTeam(problem, team);
        });
      }

      solutionsGridEl.appendChild(article);
    });
  }

  function wireForm(problem) {
    if (!formEl || !problem) return;

    formEl.addEventListener("submit", (event) => {
      event.preventDefault();
      const proposerInput = document.getElementById("proposerName");
      const ownerEmailInput = document.getElementById("ownerEmail");
      const titleInput = document.getElementById("solutionTitle");
      const summaryInput = document.getElementById("solutionSummary");
      const rolesInput = document.getElementById("neededRoles");
      if (!proposerInput || !ownerEmailInput || !titleInput || !summaryInput || !rolesInput) return;

      const proposer = proposerInput.value.trim();
      const ownerEmail = ownerEmailInput.value.trim();
      const title = titleInput.value.trim();
      const summary = summaryInput.value.trim();
      const roles = rolesInput.value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .slice(0, 8);

      if (!proposer || !title || !summary || roles.length === 0) return;
      if (ownerEmail && !sanitizeEmail(ownerEmail)) {
        alert("Owner email format looks invalid.");
        return;
      }

      const map = loadUserTeamMap();
      const teams = getUserTeamsForProblem(problem.id, map);
      teams.unshift({
        id: `${problem.id}-team-${Date.now()}`,
        problemId: problem.id,
        solutionTitle: title,
        summary,
        roles,
        ownerName: proposer,
        ownerEmail: ownerEmail || "",
        members: [
          {
            name: proposer,
            email: ownerEmail || "",
            joinedAt: Date.now(),
            joinedByCurrentUser: true,
          },
        ],
        createdAt: Date.now(),
        ownedByCurrentUser: true,
        joinedByCurrentUser: true,
      });
      saveTeamsForProblem(problem.id, teams, map);
      saveCurrentUser(proposer, ownerEmail || "");
      formEl.reset();
      renderSolutionsForProblem(problem);
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", (event) => {
      searchTerm = event.target.value.trim().toLowerCase();
      if (selectedProblem) {
        renderSolutionsForProblem(selectedProblem);
      } else {
        renderDirectory();
      }
    });
  }

  if (!selectedProblem) {
    renderDirectory();
    return;
  }

  renderSolutionsForProblem(selectedProblem);
  wireForm(selectedProblem);
}

function renderProblemPage() {
  const detailEl = document.getElementById("problemDetail");
  if (!detailEl) return;

  const params = new URLSearchParams(window.location.search);
  const problemId = params.get("id");
  const problem = problemId ? getProblemById(problemId) : null;

  if (!problem) {
    detailEl.innerHTML = `
      <h1>Problem Not Found</h1>
      <p>The requested issue could not be found. Run the scraper to regenerate live issue data.</p>
      <a class="primary-btn" href="discover.html">Back to Discover</a>
    `;
    return;
  }

  const teamCount = getTeamCountForProblem(problem);
  const sourceSubreddits = Array.isArray(problem.sourceSubreddits) ? problem.sourceSubreddits : [];
  const complaints = Array.isArray(problem.complaints) ? problem.complaints : [];
  const complaintTotal = Number(problem.complaintCount || complaints.length || 0);
  const sourcePlatform = escapeHtml(problem.sourcePlatform || "Reddit");
  const sourceMeta = sourceSubreddits.length > 0
    ? `<p>Sources: ${sourcePlatform} across ${sourceSubreddits.length} subreddits (${escapeHtml(sourceSubreddits.map((s) => `r/${s}`).join(", "))})</p>`
    : `<p>Source: ${sourcePlatform}</p>`;

  const complaintsMarkup = complaints.length > 0
    ? complaints
      .map((complaint) => {
        const text = escapeHtml(complaint.text || "");
        const subreddit = escapeHtml(complaint.subreddit || "unknown");
        const score = Number(complaint.score || 0);
        const date = formatDateFromUnix(complaint.createdUtc);
        const postTitle = escapeHtml(complaint.postTitle || "Reddit thread");
        const url = safeUrl(complaint.sourceUrl);
        const dateLabel = date ? `<span>${escapeHtml(date)}</span>` : "";
        return `
          <li class="complaint-item">
            <p class="complaint-text">${text}</p>
            <div class="complaint-meta">
              <span>r/${subreddit}</span>
              <span>Score ${score}</span>
              ${dateLabel}
              <span>${postTitle}</span>
              <a href="${url}" target="_blank" rel="noopener noreferrer">Source</a>
            </div>
          </li>
        `;
      })
      .join("")
    : `<li class="complaint-item"><p class="complaint-text">No complaint evidence loaded for this issue.</p></li>`;

  detailEl.innerHTML = `
    <h1>${escapeHtml(problem.title)}</h1>
    <div class="detail-tag-row">
      <span class="team-tag">${escapeHtml(problem.sector)}</span>
      <span class="team-tag">${Number(problem.interested || 0)} people interested</span>
      <span class="team-tag">${teamCount} teams forming</span>
      <span class="team-tag">${complaintTotal} complaint comments</span>
      <span class="team-tag">Demand: ${escapeHtml(problem.demand || "unknown")}</span>
    </div>
    <p>${escapeHtml(problem.summary || "")}</p>
    ${sourceMeta}
    <section class="complaints-panel">
      <h2>Individual Complaints</h2>
      <ul class="complaint-list">
        ${complaintsMarkup}
      </ul>
    </section>
    <div class="card-actions">
      <a class="primary-btn" href="solutions.html?problem=${encodeURIComponent(problem.id)}">View Solutions</a>
      <a class="ghost-btn" href="submit.html">Propose Solution</a>
    </div>
  `;
}

function initSubmitForm() {
  const form = document.getElementById("submitForm");
  if (!form) return;

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    alert("Problem submitted locally for the MVP demo.");
    form.reset();
  });
}

initFeedPage();
renderSolutionsPage();
renderProblemPage();
initSubmitForm();

if (page === "submit") {
  const searchInput = document.getElementById("searchInput");
  if (searchInput) searchInput.disabled = true;
}
