window.PollDatabase = (() => {
    const CLIENT_ID_KEY = "thisOrThatClientId";

    function getClientId() {
        let clientId = localStorage.getItem(CLIENT_ID_KEY);
        if (!clientId) {
            clientId = crypto.randomUUID();
            localStorage.setItem(CLIENT_ID_KEY, clientId);
        }
        return clientId;
    }

    async function request(url, options) {
        const response = await fetch(url, options);
        let data;

        try {
            data = await response.json();
        } catch {
            throw new Error("The server returned an invalid response.");
        }

        if (!response.ok) {
            throw new Error(data.error || "The database request failed.");
        }
        return data;
    }

    function getPolls(ownerId) {
        const params = new URLSearchParams({ voterId: getClientId() });
        if (ownerId) params.set("ownerId", ownerId);
        return request(`/api/polls?${params.toString()}`)
            .then(data => data.polls);
    }

    function createPoll(poll) {
        return request("/api/polls", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                ...poll,
                ownerId: getClientId()
            })
        }).then(data => data.poll);
    }

    function castVote(pollId, optionIndex) {
        return request(`/api/polls/${encodeURIComponent(pollId)}/votes`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                voterId: getClientId(),
                optionIndex
            })
        }).then(data => data.poll);
    }

    function getBuiltinVotes(pollId) {
        const params = new URLSearchParams({ voterId: getClientId() });
        return request(
            `/api/builtin-polls/${encodeURIComponent(pollId)}/votes?${params}`
        );
    }

    function castBuiltinVote(pollId, optionIndex) {
        return request(
            `/api/builtin-polls/${encodeURIComponent(pollId)}/votes`,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    voterId: getClientId(),
                    optionIndex
                })
            }
        );
    }

    function deletePoll(pollId) {
        const params = new URLSearchParams({ ownerId: getClientId() });
        return request(
            `/api/polls/${encodeURIComponent(pollId)}?${params.toString()}`,
            { method: "DELETE" }
        );
    }

    return {
        getClientId,
        getPolls,
        createPoll,
        castVote,
        getBuiltinVotes,
        castBuiltinVote,
        deletePoll
    };
})();
