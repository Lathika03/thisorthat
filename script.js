
const defaultPolls = [
    { id: 1, a: "☕ Coffee", b: "🍵 Tea", category: "food" },
    { id: 2, a: "🍕 Pizza", b: "🍔 Burger", category: "food" },
    { id: 3, a: "🐱 Cats", b: "🐶 Dogs", category: "lifestyle" },
    { id: 4, a: "🏖️ Beach", b: "🏔️ Mountains", category: "travel" }
];

function read(key, fallback) {
    try {
        const value = localStorage.getItem(key);
        return value === null ? fallback : JSON.parse(value);
    } catch {
        return fallback;
    }
}

function write(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

function getPolls() {
    return read("polls", defaultPolls);
}

function getPoll() {
    const id = Number(new URLSearchParams(location.search).get("id")) || 1;
    return getPolls().find(p => p.id === id) || getPolls()[0];
}

function renderExplore() {
    const target = document.getElementById("choices");
    if (!target) return;

    const query = document.getElementById("search").value.toLowerCase();
    const category = document.getElementById("category").value;

    target.replaceChildren();

    getPolls()
        .filter(p => `${p.a} ${p.b}`.toLowerCase().includes(query))
        .filter(p => category === "all" || p.category === category)
        .forEach(p => {
            const card = document.createElement("div");
            card.className = "card";

            const title = document.createElement("h2");
            title.textContent = `${p.a} vs ${p.b}`;

            const link = document.createElement("a");
            link.className = "btn";
            link.href = `vote.html?id=${p.id}`;
            link.textContent = "Vote Now";

            const save = document.createElement("button");
            save.textContent = "♡ Save";
            save.onclick = () => {
                const saved = read("saved", []);
                if (!saved.includes(p.id)) saved.push(p.id);
                write("saved", saved);
                save.textContent = "♥ Saved";
            };

            card.append(title, link, save);
            target.appendChild(card);
        });
}

function filterChoices() {
    renderExplore();
}

function castVote(option) {
    const poll = getPoll();
    if (!poll) return;

    const votes = read("votes", {});
    const voterKey = `voted_${poll.id}`;

    if (localStorage.getItem(voterKey)) {
        document.getElementById("message").textContent =
            "You have already voted on this device for this choice.";
        return;
    }

    if (!votes[poll.id]) votes[poll.id] = { A: 0, B: 0 };

    votes[poll.id][option]++;
    write("votes", votes);
    localStorage.setItem(voterKey, option);

    location.href = `results.html?id=${poll.id}`;
}

function renderResults() {
    const aLabel = document.getElementById("labelA");
    if (!aLabel) return;

    const poll = getPoll();
    if (!poll) return;

    const votes = read("votes", {});
    const count = votes[poll.id] || { A: 0, B: 0 };
    const total = count.A + count.B;
    const aPercent = total ? Math.round(count.A / total * 100) : 0;
    const bPercent = total ? 100 - aPercent : 0;

    document.getElementById("resultQuestion").textContent =
        `${poll.a} vs ${poll.b}`;

    aLabel.textContent = `${poll.a}: ${aPercent}%`;
    document.getElementById("labelB").textContent =
        `${poll.b}: ${bPercent}%`;

    document.getElementById("barA").style.width = `${aPercent}%`;
    document.getElementById("barB").style.width = `${bPercent}%`;

    document.getElementById("totalVotes").textContent =
        `Total votes: ${total}`;
}

function createChoice(event) {
    event.preventDefault();

    const a = document.getElementById("newA").value.trim();
    const b = document.getElementById("newB").value.trim();
    const category = document.getElementById("newCategory").value;

    if (!a || !b || a.toLowerCase() === b.toLowerCase()) {
        document.getElementById("createMessage").textContent =
            "Enter two different options.";
        return;
    }

    const polls = getPolls();
    const id = Math.max(0, ...polls.map(p => p.id)) + 1;

    polls.push({ id, a, b, category });
    write("polls", polls);

    document.getElementById("createMessage").textContent =
        "Choice created successfully!";

    event.target.reset();
}

function renderSaved() {
    const target = document.getElementById("savedChoices");
    if (!target) return;

    const saved = read("saved", []);
    target.replaceChildren();

    getPolls().filter(p => saved.includes(p.id)).forEach(p => {
        const card = document.createElement("div");
        card.className = "card";

        const title = document.createElement("h2");
        title.textContent = `${p.a} vs ${p.b}`;

        const link = document.createElement("a");
        link.className = "btn";
        link.href = `vote.html?id=${p.id}`;
        link.textContent = "Open Poll";

        const remove = document.createElement("button");
        remove.textContent = "Remove";
        remove.onclick = () => {
            write("saved", read("saved", []).filter(id => id !== p.id));
            renderSaved();
        };

        card.append(title, link, remove);
        target.appendChild(card);
    });

    if (!saved.length) {
        target.textContent = "No saved choices yet. Explore and save a poll!";
    }
}

function saveSettings() {
    const name = document.getElementById("settingName").value.trim();
    const theme = document.getElementById("theme").value;

    if (name) write("userName", name);
    write("theme", theme);
    applySettings();

    document.getElementById("settingsMessage").textContent =
        "Settings saved!";
}

function applySettings() {
    const theme = read("theme", "light");

    document.body.style.background =
        theme === "dark" ? "#17172b" : "";

    document.body.style.color =
        theme === "dark" ? "#ffffff" : "";

    const settingName = document.getElementById("settingName");
    if (settingName) {
        settingName.value = read("userName", "");
    }

    const themeSelect = document.getElementById("theme");
    if (themeSelect) themeSelect.value = theme;

    const profileName = document.getElementById("profileName");
    if (profileName) {
        profileName.textContent = read("userName", "Guest User");
    }
}

function renderProfile() {
    const votes = read("votes", {});
    const polls = getPolls();
    const saved = read("saved", []);

    const voteCount = Object.values(votes)
        .reduce((sum, v) => sum + v.A + v.B, 0);

    const votesEl = document.getElementById("activityVotes");
    if (votesEl) votesEl.textContent = `Votes cast: ${voteCount}`;

    const createdEl = document.getElementById("activityCreated");
    if (createdEl) {
        createdEl.textContent =
            `Choices created: ${Math.max(0, polls.length - defaultPolls.length)}`;
    }

    const savedEl = document.getElementById("activitySaved");
    if (savedEl) savedEl.textContent = `Saved choices: ${saved.length}`;
}

/* ========================================
   ADDED: COMMUNITY POLL SUPPORT
   Existing functions above are preserved.
======================================== */

const CUSTOM_POLLS_KEY = "thisOrThatCustomPolls";

function getCustomPolls() {
    const polls = read(CUSTOM_POLLS_KEY, []);
    return Array.isArray(polls) ? polls : [];
}

function getCustomPoll(id) {
    return getCustomPolls().find(
        poll => String(poll.id) === String(id)
    );
}

function saveCustomPolls(polls) {
    write(CUSTOM_POLLS_KEY, polls);
}

function renderCommunityPolls() {
    const target = document.getElementById("communityPolls");
    if (!target) return;

    const emptyMessage = document.getElementById("noCommunityPolls");
    const polls = getCustomPolls();

    target.replaceChildren();

    if (emptyMessage) {
        emptyMessage.style.display = polls.length ? "none" : "block";
    }

    polls.slice().reverse().forEach(poll => {
        const card = document.createElement("article");
        card.className = "community-card";

        const category = document.createElement("span");
        category.className = "community-category";
        category.textContent = (poll.category || "Other").toUpperCase();

        const title = document.createElement("h3");
        title.textContent = poll.question || "Community Poll";

        card.append(category, title);

        const optionsBox = document.createElement("div");
        optionsBox.className = "community-options";

        const options = Array.isArray(poll.options) ? poll.options : [];

        options.forEach(option => {
            const optionBox = document.createElement("div");
            optionBox.className = "community-option";

            const img = document.createElement("img");
            img.alt = option.name || "Poll option";
            img.loading = "lazy";
            img.src = option.image ||
                "https://placehold.co/400x250/eee8ff/6555f5?text=No+Image";

            const name = document.createElement("h4");
            name.textContent = option.name || "Option";

            optionBox.append(img, name);
            optionsBox.appendChild(optionBox);
        });

        card.appendChild(optionsBox);

        if (poll.description) {
            const description = document.createElement("p");
            description.className = "community-description";
            description.textContent = poll.description;
            card.appendChild(description);
        }

        const counts = Array.isArray(poll.votes) ? poll.votes : [];
        const totalVotes = counts.reduce(
            (sum, value) => sum + (Number(value) || 0), 0
        );

        const voteInfo = document.createElement("p");
        voteInfo.className = "community-votes";
        voteInfo.textContent = `🗳️ Total votes: ${totalVotes}`;
        card.appendChild(voteInfo);

        const actions = document.createElement("div");
        actions.className = "community-actions";

        const voteLink = document.createElement("a");
        voteLink.href =
            "custom-vote.html?id=" + encodeURIComponent(poll.id);
        voteLink.textContent = "Vote Now →";

        const resultsLink = document.createElement("a");
        resultsLink.href =
            "custom-results.html?id=" + encodeURIComponent(poll.id);
        resultsLink.className = "community-results-link";
        resultsLink.textContent = "View Results →";

        actions.append(voteLink, resultsLink);
        card.appendChild(actions);

        target.appendChild(card);
    });
}

/* ADDED: CUSTOM POLL VOTING */

function castCustomVote(optionIndex) {
    const id = new URLSearchParams(location.search).get("id");
    const poll = getCustomPoll(id);

    if (!poll) {
        const message = document.getElementById("customVoteMessage");
        if (message) message.textContent = "Poll not found.";
        return;
    }

    const voterKey = `thisOrThatCustomVote_${poll.id}`;

    if (localStorage.getItem(voterKey)) {
        const message = document.getElementById("customVoteMessage");
        if (message) message.textContent = "You have already voted on this device.";
        return;
    }

    if (!Array.isArray(poll.votes)) {
        poll.votes = poll.options.map(() => 0);
    }

    if (
        optionIndex < 0 ||
        optionIndex >= poll.options.length
    ) {
        return;
    }

    poll.votes[optionIndex] = (Number(poll.votes[optionIndex]) || 0) + 1;

    const polls = getCustomPolls();
    const pollIndex = polls.findIndex(
        item => String(item.id) === String(poll.id)
    );

    if (pollIndex !== -1) {
        polls[pollIndex] = poll;
        saveCustomPolls(polls);
    }

    localStorage.setItem(voterKey, String(optionIndex));

    location.href =
        "custom-results.html?id=" + encodeURIComponent(poll.id);
}

/* ADDED: CUSTOM POLL RESULTS */

function renderCustomResults() {
    const target = document.getElementById("customResults");
    if (!target) return;

    const id = new URLSearchParams(location.search).get("id");
    const poll = getCustomPoll(id);

    target.replaceChildren();

    if (!poll) {
        target.textContent = "Poll not found.";
        return;
    }

    const title = document.getElementById("customResultQuestion");
    if (title) title.textContent = poll.question || "Community Poll";

    const options = Array.isArray(poll.options) ? poll.options : [];
    const votes = Array.isArray(poll.votes) ? poll.votes : [];
    const total = options.reduce(
        (sum, option, index) => sum + (Number(votes[index]) || 0), 0
    );

    options.forEach((option, index) => {
        const count = Number(votes[index]) || 0;
        const percent = total ? Math.round(count / total * 100) : 0;

        const card = document.createElement("div");
        card.className = "card";

        const label = document.createElement("h3");
        label.textContent = `${option.name || "Option"} — ${percent}%`;

        const countText = document.createElement("p");
        countText.textContent = `${count} vote(s)`;

        const bar = document.createElement("div");
        bar.className = "bar";

        const fill = document.createElement("div");
        fill.className = "fill";
        fill.style.width = `${percent}%`;

        bar.appendChild(fill);
        card.append(label, countText, bar);
        target.appendChild(card);
    });

    const totalVotes = document.getElementById("customTotalVotes");
    if (totalVotes) totalVotes.textContent = `Total votes: ${total}`;
}

/* ADDED: CUSTOM POLL EVENT HANDLERS */

document.addEventListener("DOMContentLoaded", () => {
    renderCommunityPolls();
    renderCustomResults();
});

window.addEventListener("storage", event => {
    if (
        event.key === CUSTOM_POLLS_KEY ||
        event.key === "thisOrThatCustomPolls"
    ) {
        renderCommunityPolls();
        renderCustomResults();
    }
});

/* ORIGINAL DOM CONTENT LOADED HANDLER */

document.addEventListener("DOMContentLoaded", () => {
    const poll = getPoll();

    const optionA = document.getElementById("optionA");
    const optionB = document.getElementById("optionB");

    if (optionA && poll) {
        optionA.textContent = poll.a;
        optionB.textContent = poll.b;
    }

    const form = document.getElementById("createForm");
    if (form) form.addEventListener("submit", createChoice);

    const search = document.getElementById("search");
    if (search) {
        search.addEventListener("input", filterChoices);
    }

    const category = document.getElementById("category");
    if (category) {
        category.addEventListener("change", filterChoices);
    }

    renderExplore();
    renderResults();
    renderSaved();
    renderProfile();
    applySettings();
});
