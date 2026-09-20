// Max Node for Max (node.script) object -- receives the live_state_json
// message from live_state_reader.js and POSTs it to Stage L's Python
// endpoint, then outputs KENN's grounded suggestion back into the patch.
//
// Talks only to the local server already running as part of this codebase
// (business/app/server.py, started via `./audio-too server` or
// `python main.py server`) -- no new server process, per Stage L's own
// design (docs/AUDIO_MVP_MASTER_PLAN.md Sec.L4 items 1/3).
//
// NOT YET VERIFIED INSIDE A REAL MAX SESSION -- written from documented
// Node for Max (max-api) conventions, not tested here. Jack: run
// `npm install max-api` inside this folder before wiring this into a
// node.script object (Max 8+ ships Node, but the max-api package itself is
// not bundled by default) -- see README.md.

const Max = require("max-api");
const http = require("http");

// Port note: business/app/server.py (the KENN dashboard / ableton_bridge
// server) listens on 8090 by default, and is what this endpoint was added
// to. An earlier, archived plan (docs/archive/SYSTEM_PLAN.md) described a
// similar M4L button targeting Thursday's own server on 8092 instead --
// that server does not currently have the sys.path wiring this endpoint's
// KENN imports need, so 8090 is the one that actually works today. Change
// this if you'd rather run it through Thursday's server once that's wired.
const SERVER_HOST = "127.0.0.1";
const SERVER_PORT = 8090;
const SERVER_PATH = "/api/ableton/live-suggestion";

Max.addHandler("live_state_json", (jsonString) => {
    let body;
    try {
        body = JSON.parse(jsonString);
    } catch (err) {
        Max.outlet("error", "Could not parse live state JSON: " + err.message);
        return;
    }

    const data = JSON.stringify(body);
    const req = http.request(
        {
            host: SERVER_HOST,
            port: SERVER_PORT,
            path: SERVER_PATH,
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(data),
            },
        },
        (res) => {
            let raw = "";
            res.on("data", (chunk) => (raw += chunk));
            res.on("end", () => {
                try {
                    const result = JSON.parse(raw);
                    if (result.weak_match || result.found === false) {
                        Max.outlet("suggestion", "KENN isn't confident here -- no grounded suggestion found.");
                    } else {
                        Max.outlet("suggestion", result.answer || "(no answer text)");
                    }
                } catch (err) {
                    Max.outlet("error", "Could not parse server response: " + err.message);
                }
            });
        }
    );
    req.on("error", (err) => {
        Max.outlet("error", "Could not reach the local server: " + err.message + " -- is it running?");
    });
    req.write(data);
    req.end();
});
