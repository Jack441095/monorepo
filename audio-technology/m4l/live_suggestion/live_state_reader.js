// Max `js` object -- reads a small, fixed slice of Live Object Model (LOM)
// state for the currently selected track and outputs it as JSON for
// live_suggestion_client.js (a node.script object) to forward to KENN.
//
// Read-only by construction: every call below is a LiveAPI .get()/.getcount()
// getter. There is no .set() or .call() anywhere in this file, and there
// must never be one added here -- see Stage L Sec.L5 in
// docs/AUDIO_MVP_MASTER_PLAN.md for why that boundary is the whole point of
// this MVP (KENN shows a suggestion; the user applies it themselves via
// their own normal Ableton interaction).
//
// NOT YET VERIFIED INSIDE A REAL MAX/ABLETON SESSION -- written from
// Cycling '74's documented LiveAPI JS conventions, not tested here (this
// assistant has no way to run Max or Ableton). Jack: please open this in
// Max's [js] object, hit the "Get Selected Track" button below, and confirm
// the outlet actually prints a sane live_state_json payload before wiring
// it to anything else. See README.md in this folder for the full checklist.

autowatch = 1;
inlets = 1;
outlets = 1;

function bang() {
    try {
        var trackApi = new LiveAPI("live_set view selected_track");
        var trackNameResult = trackApi.get("name");
        var trackName = (trackNameResult && trackNameResult[0]) || "Unnamed Track";

        var deviceChain = [];
        var keyParams = {};
        var deviceCount = trackApi.getcount("devices");

        for (var i = 0; i < deviceCount; i++) {
            var deviceApi = new LiveAPI("live_set view selected_track devices " + i);
            var deviceNameResult = deviceApi.get("name");
            var deviceName = (deviceNameResult && deviceNameResult[0]) || ("Device " + i);
            deviceChain.push(deviceName);

            var paramCount = deviceApi.getcount("parameters");
            for (var p = 0; p < paramCount; p++) {
                var paramApi = new LiveAPI(
                    "live_set view selected_track devices " + i + " parameters " + p
                );
                var paramNameResult = paramApi.get("name");
                var paramValueResult = paramApi.get("value");
                var paramName = paramNameResult && paramNameResult[0];
                if (paramName) {
                    keyParams[deviceName + "." + paramName] = paramValueResult && paramValueResult[0];
                }
            }
        }

        var payload = {
            track_name: trackName,
            device_chain: deviceChain,
            key_params: keyParams
        };

        outlet(0, "live_state_json", JSON.stringify(payload));
    } catch (err) {
        outlet(0, "error", "Could not read live session state: " + err.message);
    }
}
