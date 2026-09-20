/**
 * KENN Audio Dev Agent VS Code Extension
 * Provides inline code analysis, DSP advice, and real-time thread safety checks.
 */

const vscode = require('vscode');
const http = require('http');

const KENN_SERVER_URL = 'http://127.0.0.1:8090/api/audio-dev';

function activate(context) {
    let disposable = vscode.commands.registerCommand('kenn.askAudioDev', async function () {
        const editor = vscode.window.activeTextEditor;
        let selectedCode = '';
        let language = 'cpp';

        if (editor) {
            selectedCode = editor.document.getText(editor.selection) || editor.document.getText();
            language = editor.document.languageId;
        }

        const query = await vscode.window.showInputBox({
            prompt: "Ask KENN Audio Dev Agent (e.g. 'How do I vectorize this gain loop safely?')",
            placeHolder: "Enter query or leave blank for code audit"
        });

        if (query === undefined) return; // User cancelled

        const effectiveQuery = query.trim() || "Analyze this audio code for real-time safety, memory allocations, and performance optimization.";

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "KENN Audio Dev Agent thinking...",
            cancellable: false
        }, async () => {
            try {
                const response = await queryKennAudioDev(effectiveQuery, selectedCode, language);
                displayResult(response);
            } catch (err) {
                vscode.window.showErrorMessage(`KENN Agent Error: ${err.message}`);
            }
        });
    });

    context.subscriptions.push(disposable);

    // Register DSP Snippet Generator Command
    let snippetDisposable = vscode.commands.registerCommand('kenn.insertDspSnippet', async function () {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('No active editor to insert DSP snippet.');
            return;
        }

        const items = [
            { label: 'C++ SIMD Vectorized Gain Loop', description: 'JUCE FloatVectorOperations::multiply', snippet: 'juce::FloatVectorOperations::multiply(buffer.getWritePointer(ch), gain, buffer.getNumSamples());\n' },
            { label: 'C++ Lock-Free Ring Buffer', description: 'Single-Producer Single-Consumer Audio Queue', snippet: 'template <typename T, size_t Capacity>\nclass LockFreeAudioQueue {\npublic:\n    bool push(const T& val) noexcept {\n        auto w = writeIdx.load(std::memory_order_relaxed);\n        if ((w + 1) % Capacity == readIdx.load(std::memory_order_acquire)) return false;\n        buffer[w] = val;\n        writeIdx.store((w + 1) % Capacity, std::memory_order_release);\n        return true;\n    }\nprivate:\n    std::array<T, Capacity> buffer;\n    std::atomic<size_t> writeIdx{0}, readIdx{0};\n};\n' },
            { label: 'C++ JUCE Biquad Filter', description: 'JUCE dsp::IIR::Filter process loop', snippet: 'juce::dsp::AudioBlock<float> block(buffer);\njuce::dsp::ProcessContextReplacing<float> context(block);\nfilter.process(context);\n' },
            { label: 'Python Mid-Side Matrix', description: 'Convert L/R numpy channels to M/S', snippet: 'mid = 0.5 * (left + right)\nside = 0.5 * (left - right)\n' },
            { label: 'Python True-Peak Calculation', description: 'NumPy 4x oversampled true peak estimator', snippet: 'import numpy as np\nfrom scipy.signal import resample_poly\n\ndef calculate_true_peak(left: np.ndarray, right: np.ndarray) -> float:\n    l_4x = resample_poly(left, 4, 1)\n    r_4x = resample_poly(right, 4, 1)\n    peak_lin = max(np.max(np.abs(l_4x)), np.max(np.abs(r_4x)))\n    return float(20.0 * np.log10(max(1e-7, peak_lin)))\n' }
        ];

        const selection = await vscode.window.showQuickPick(items, {
            placeHolder: 'Select Audio DSP Code Snippet to Insert'
        });

        if (selection) {
            editor.edit(editBuilder => {
                editBuilder.insert(editor.selection.active, selection.snippet);
            });
        }
    });

    context.subscriptions.push(snippetDisposable);

    // Register Real-time Audio Thread Safety Hover Provider
    let hoverDisposable = vscode.languages.registerHoverProvider(['cpp', 'python'], {
        provideHover(document, position) {
            const lineText = document.lineAt(position.line).text;
            const unsafePatterns = [
                { pattern: /\b(malloc|free|realloc)\b/, warning: 'Heap Memory Allocation (malloc/free)' },
                { pattern: /\bnew\s+[A-Za-z0-9_]+/, warning: 'Dynamic Object Instantiation (new operator)' },
                { pattern: /\b(std::mutex|mutex\.lock|pthread_mutex_lock)\b/, warning: 'Mutex Blocking Lock' },
                { pattern: /\b(std::cout|printf|sys\.stdout)\b/, warning: 'I/O Console Output (Blocking syscall)' }
            ];

            for (const item of unsafePatterns) {
                if (item.pattern.test(lineText)) {
                    const contents = new vscode.MarkdownString();
                    contents.appendMarkdown(`⚠️ **Real-Time Audio Safety Warning**: \`${item.warning}\` detected!\n\n`);
                    contents.appendMarkdown(`Performing blocking or allocating operations inside an audio render thread causes **buffer underruns and audio glitches**. Use lock-free atomics or pre-allocated pools instead.`);
                    return new vscode.Hover(contents);
                }
            }
            return null;
        }
    });

    context.subscriptions.push(hoverDisposable);
}

function queryKennAudioDev(query, codeContext, language) {
    return new Promise((resolve, reject) => {
        const payload = JSON.stringify({
            query: query,
            code_context: codeContext,
            language: language
        });

        const req = http.request(KENN_SERVER_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(payload)
            }
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                if (res.statusCode >= 200 && res.statusCode < 300) {
                    try {
                        resolve(JSON.parse(data));
                    } catch (e) {
                        reject(new Error("Invalid JSON from KENN server."));
                    }
                } else {
                    reject(new Error(`HTTP ${res.statusCode}: ${data}`));
                }
            });
        });

        req.on('error', err => reject(err));
        req.write(payload);
        req.end();
    });
}

function displayResult(result) {
    const panel = vscode.window.createWebviewPanel(
        'kennAudioDev',
        'KENN Audio Dev Advice',
        vscode.ViewColumn.Two,
        { enableScripts: true }
    );

    let warningsHtml = '';
    if (result.realtime_warnings && result.realtime_warnings.length > 0) {
        warningsHtml = `
            <div style="background: rgba(248,113,113,0.15); border: 1px solid #f87171; border-radius: 6px; padding: 12px; margin-bottom: 16px;">
                <h4 style="color: #f87171; margin-top:0;">⚠️ Real-Time Thread Safety Warnings</h4>
                <ul>
                    ${result.realtime_warnings.map(w => `<li style="color:#f87171;">${w}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    panel.webview.html = `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: -apple-system, sans-serif; padding: 16px; background: #0b0b0b; color: #e4e4e7; line-height: 1.6; }
                h2 { color: #60a5fa; border-bottom: 1px solid #2a2a2a; padding-bottom: 8px; }
                .citation { background: #181818; border: 1px solid #363636; border-radius: 4px; padding: 6px 10px; margin: 4px 0; font-size: 12px; color: #a78bfa; }
                pre { background: #111111; padding: 12px; border-radius: 6px; overflow-x: auto; font-family: monospace; border: 1px solid #2a2a2a; }
            </style>
        </head>
        <body>
            <h2>✦ KENN Audio Dev Advice</h2>
            ${warningsHtml}
            <div>
                <h3>Answer</h3>
                <p>${(result.advice || 'No advice returned.').replace(/\n/g, '<br>')}</p>
            </div>
            ${result.citations && result.citations.length > 0 ? `
                <h3>Grounded Citations</h3>
                ${result.citations.map(c => `<div class="citation">📚 ${c}</div>`).join('')}
            ` : ''}
        </body>
        </html>
    `;
}

function deactivate() {}

module.exports = {
    activate,
    deactivate
};
