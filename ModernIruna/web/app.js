document.addEventListener("DOMContentLoaded", () => {
    // UI Elements
    const loginScreen = document.getElementById("login-screen");
    const dashScreen = document.getElementById("dashboard-screen");
    const connectBtn = document.getElementById("connect-btn");
    const urlInput = document.getElementById("mageurl-input");
    const statusMsg = document.getElementById("login-status");

    // Controls
    const modeBtns = document.querySelectorAll(".mode-btn");
    const pauseBtn = document.getElementById("pause-btn");
    const hexInput = document.getElementById("hex-input");
    const injectBtn = document.getElementById("inject-btn");
    const mapNameSpan = document.getElementById("map-name");
    
    // Components
    const radarList = document.getElementById("radar-list");
    const inventoryList = document.getElementById("inventory-list");
    const terminal = document.getElementById("terminal");

    let isConnected = false;
    let pollInterval = null;
    
    // Always poll logs so they show up on login screen too
    setInterval(fetchLogs, 500);
    
    // Fetch version on load
    fetch("/api/state")
        .then(r => r.json())
        .then(data => {
            const verEl = document.getElementById("app-version");
            if (verEl && data.version) {
                verEl.textContent = `Version: ${data.version}`;
            }
        }).catch(() => {});

    // --- Island Actions ---
    const fetchIslandsBtn = document.getElementById("fetch-islands-btn");
    const enterIslandBtn = document.getElementById("enter-island-btn");
    const browseStallBtn = document.getElementById("browse-stall-btn");
    
    if (fetchIslandsBtn) {
        fetchIslandsBtn.addEventListener("click", () => {
            fetch("/api/island/action", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({action: "list"})
            });
        });
    }
    
    if (enterIslandBtn) {
        enterIslandBtn.addEventListener("click", () => {
            const islandId = document.getElementById("target-island-id").value.trim();
            if (islandId) {
                fetch("/api/island/action", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({action: "enter", island_id: islandId})
                });
            }
        });
    }
    
    if (browseStallBtn) {
        browseStallBtn.addEventListener("click", () => {
            const stallUid = document.getElementById("target-stall-uid").value.trim();
            const charId = document.getElementById("target-stall-char").value.trim();
            if (stallUid && charId) {
                fetch("/api/island/action", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        action: "browse_stall",
                        char_id: charId,
                        stall_uid: stallUid
                    })
                });
            }
        });
    }

    // --- Login ---
    connectBtn.addEventListener("click", () => {
        const url = urlInput.value.trim();
        if(!url) return;
        
        connectBtn.disabled = true;
        statusMsg.textContent = "Negotiating Neural Link...";

        fetch("/api/connect", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({url})
        })
        .then(res => res.json())
        .then(data => {
            // fast-polling state
            pollInterval = setInterval(fetchState, 500); 
        })
        .catch(err => {
            statusMsg.textContent = "Fatal: Server unverified.";
            connectBtn.disabled = false;
        });
    });

    const connectIslandBtn = document.getElementById("connect-island-btn");
    const emailInput = document.getElementById("email-input");
    if(connectIslandBtn) {
        connectIslandBtn.addEventListener("click", () => {
            const url = urlInput.value.trim();
            const email = emailInput ? emailInput.value.trim() : "";
            if(!url || !email) {
                statusMsg.textContent = "Error: MageURL and Email are required for Island Mode.";
                return;
            }
            
            connectIslandBtn.disabled = true;
            statusMsg.textContent = "Initializing Island Neural Link...";

            fetch("/api/island/connect", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({url, email})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    pollInterval = setInterval(fetchState, 500); 
                    isConnected = true;
                    loginScreen.classList.remove("active");
                    loginScreen.classList.add("hidden");
                    const islandScreen = document.getElementById("island-dashboard-screen");
                    if(islandScreen) {
                        islandScreen.classList.remove("hidden");
                        islandScreen.classList.add("active");
                    }
                } else {
                    statusMsg.textContent = "Island Login Failed: " + (data.error || "Unknown Error");
                    connectIslandBtn.disabled = false;
                }
            })
            .catch(err => {
                statusMsg.textContent = "Fatal: Server unverified.";
                connectIslandBtn.disabled = false;
            });
        });
    }

    function transitionToDashboard(isIsland = false) {
        if(isConnected) return;
        isConnected = true;
        loginScreen.classList.remove("active");
        loginScreen.classList.add("hidden");
        
        // Wait for class transitions
        setTimeout(() => {
            if(isIsland) {
                const islandScreen = document.getElementById("island-dashboard-screen");
                if(islandScreen) {
                    islandScreen.classList.remove("hidden");
                    islandScreen.classList.add("active");
                }
            } else {
                dashScreen.classList.remove("hidden");
                dashScreen.classList.add("active");
            }
            
            // Fetch initial log history so the terminal isn't blank on refresh
            fetch("/api/logs/history")
            .then(r => r.json())
            .then(data => {
                if(data.logs && data.logs.length > 0) {
                    terminal.innerHTML = "";
                    data.logs.forEach(log => {
                        let span = document.createElement("span");
                        span.textContent = log;
                        if(log.includes("<-")) span.className = "log-recv";
                        else if (log.includes("->")) span.className = "log-send";
                        else if (log.includes("[!]")) span.className = "log-warn";
                        terminal.appendChild(span);
                    });
                    terminal.scrollTop = terminal.scrollHeight;
                }
            });
        }, 100);
    }

    // --- Polling Logic ---
    function fetchState() {
        fetch("/api/state")
        .then(r => r.json())
        .then(data => {
            if(data.connected && !isConnected) {
                transitionToDashboard(data.is_island_mode);
            }

            if(isConnected) {
                updateControls(data);
                updateParty(data);
                updateInventory(data);
                if (data.is_island_mode) {
                    updateIslandUI(data);
                }
                if (data.currentMap) {
                    mapNameSpan.textContent = data.currentMap;
                }
            }
        });
    }

    function updateIslandUI(data) {
        const stallList = document.getElementById("island-stall-list");
        if (stallList) {
            if (!data.stall_items || data.stall_items.length === 0) {
                stallList.innerHTML = '<div class="inv-empty">No items loaded...</div>';
            } else {
                stallList.innerHTML = '';
                data.stall_items.forEach(it => {
                    const row = document.createElement("div");
                    row.className = "inv-row";
                    row.innerHTML = `
                        <div class="inv-info">
                            <span class="inv-name">${it.name}</span>
                            <span class="inv-id">Price: ${it.price.toLocaleString()}</span>
                        </div>
                    `;
                    stallList.appendChild(row);
                });
            }
        }
        
        const islandList = document.getElementById("island-list-view");
        if (islandList) {
            if (!data.island_list || data.island_list.length === 0) {
                islandList.innerHTML = '<div class="inv-empty">No islands loaded...</div>';
            } else {
                islandList.innerHTML = '';
                data.island_list.forEach(isl => {
                    const row = document.createElement("div");
                    row.className = "inv-row";
                    row.innerHTML = `
                        <div class="inv-info">
                            <span class="inv-name">${isl.name}</span>
                            <span class="inv-id">ID: ${isl.char_id}</span>
                        </div>
                    `;
                    islandList.appendChild(row);
                });
            }
        }
    }

    function fetchLogs() {
        fetch("/api/logs")
        .then(r => r.json())
        .then(data => {
            if(data.logs && data.logs.length > 0) {
                const loginTerminal = document.getElementById("login-terminal");
                const islandTerminal = document.getElementById("island-terminal");
                
                let isScrolledToBottom = terminal ? (terminal.scrollHeight - terminal.clientHeight <= terminal.scrollTop + 1) : false;
                let isLoginScrolled = loginTerminal ? (loginTerminal.scrollHeight - loginTerminal.clientHeight <= loginTerminal.scrollTop + 1) : false;
                let isIslandScrolled = islandTerminal ? (islandTerminal.scrollHeight - islandTerminal.clientHeight <= islandTerminal.scrollTop + 1) : false;
                
                data.logs.forEach(log => {
                    let span = document.createElement("span");
                    span.textContent = log;
                    if(log.includes("<-")) span.className = "log-recv";
                    else if (log.includes("->")) span.className = "log-send";
                    else if (log.includes("[!]")) span.className = "log-warn";
                    
                    if (terminal) terminal.appendChild(span);
                    
                    if (loginTerminal) {
                        let spanClone = span.cloneNode(true);
                        loginTerminal.appendChild(spanClone);
                    }
                    if (islandTerminal) {
                        let spanClone = span.cloneNode(true);
                        islandTerminal.appendChild(spanClone);
                    }
                });

                // Cap logs to prevent infinite DOM memory usage (browser crash)
                if (terminal) {
                    while(terminal.childNodes.length > 500) {
                        terminal.removeChild(terminal.firstChild);
                    }
                    if(isScrolledToBottom) {
                        terminal.scrollTop = terminal.scrollHeight;
                    }
                }
                
                if (loginTerminal) {
                    while(loginTerminal.childNodes.length > 500) {
                        loginTerminal.removeChild(loginTerminal.firstChild);
                    }
                    if (isLoginScrolled) {
                        loginTerminal.scrollTop = loginTerminal.scrollHeight;
                    }
                }
                
                if (islandTerminal) {
                    while(islandTerminal.childNodes.length > 500) {
                        islandTerminal.removeChild(islandTerminal.firstChild);
                    }
                    if (isIslandScrolled) {
                        islandTerminal.scrollTop = islandTerminal.scrollHeight;
                    }
                }
            }
        });
    }

    // --- API Writers ---
    function sendAction(payload) {
        fetch("/api/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        });
    }

    // --- Interaction Binding ---
    modeBtns.forEach(btn => {
        btn.addEventListener("click", (e) => {
            const mode = e.target.dataset.mode;
            sendAction({type: "set_mode", mode: mode});
        });
    });

    pauseBtn.addEventListener("click", () => {
        sendAction({type: "toggle_pause"});
    });



    injectBtn.addEventListener("click", () => {
        const hex = hexInput.value;
        if(hex) {
            sendAction({type: "inject_hex", hex: hex});
            hexInput.value = "";
        }
    });

    // Teleport
    const tpMapId = document.getElementById("tp-mapid");
    const tpX = document.getElementById("tp-x");
    const tpY = document.getElementById("tp-y");
    const tpBtn = document.getElementById("tp-btn");
    const tpStatus = document.getElementById("tp-status");

    tpBtn.addEventListener("click", () => {
        const mapId = tpMapId.value.trim();
        if(!mapId) {
            tpStatus.textContent = "Enter a map ID";
            tpStatus.className = "tp-status-msg tp-error";
            return;
        }

        const payload = {type: "teleport", map_id: parseInt(mapId)};
        const xVal = tpX.value.trim();
        const yVal = tpY.value.trim();
        if(xVal) payload.x = parseInt(xVal);
        if(yVal) payload.y = parseInt(yVal);

        sendAction(payload);
        tpStatus.textContent = "Warping to " + mapId + "...";
        tpStatus.className = "tp-status-msg tp-ok";
        setTimeout(() => { tpStatus.textContent = ""; }, 3000);
    });

    // Zimov Button
    const zimovBtn = document.getElementById("zimov-btn");
    const zimovStatus = document.getElementById("zimov-status");

    zimovBtn.addEventListener("click", () => {
        zimovBtn.disabled = true;
        zimovStatus.textContent = "Initiating Zimov Sequence...";
        zimovStatus.className = "tp-status-msg tp-ok";

        fetch("/api/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({type: "zimov_boss"})
        }).then(r => r.json()).then(data => {
            if (data.status === "error") {
                zimovStatus.textContent = data.message;
                zimovStatus.className = "tp-status-msg tp-error";
                zimovBtn.disabled = false;
            } else {
                zimovStatus.textContent = "Sequence Running...";
                setTimeout(() => { zimovStatus.textContent = ""; }, 5000);
            }
        });
    });

    // Self Heal Button
    const triggerSelfHeal = () => {
        fetch("/api/cast_skill", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ skill_hex: "1c36", uid: "self" })
        });
    };
    document.getElementById("self-heal-btn").addEventListener("click", triggerSelfHeal);
    document.getElementById("self-heal-btn-green").addEventListener("click", triggerSelfHeal);

    document.getElementById("revive-btn").addEventListener("click", () => {
        fetch("/api/revive", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        }).then(r => r.json()).then(data => {
            if (data.error) console.error(data.error);
            else console.log("Revive request sent");
        }).catch(e => console.error(e));
    });

    document.getElementById("create-pt-area-btn").addEventListener("click", () => {
        fetch("/api/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ type: "create_pt_area" })
        }).then(r => r.json()).then(data => {
            if (data.error) console.error(data.error);
            else console.log("PT Area creation initiated");
        }).catch(e => console.error(e));
    });

    document.getElementById("join-pt-area-btn").addEventListener("click", () => {
        fetch("/api/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ type: "join_pt_area" })
        }).then(r => r.json()).then(data => {
            if (data.error) console.error(data.error);
            else console.log("PT Area join initiated");
        }).catch(e => console.error(e));
    });

    // Heal Button
    const healBtn = document.getElementById("heal-btn");
    
    healBtn.addEventListener("click", () => {
        healBtn.disabled = true;
        zimovStatus.textContent = "Initiating Heal Sequence...";
        zimovStatus.className = "tp-status-msg tp-ok";

        fetch("/api/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({type: "kakeula_heal"})
        }).then(r => r.json()).then(data => {
            if (data.status === "error") {
                zimovStatus.textContent = data.message;
                zimovStatus.className = "tp-status-msg tp-error";
                healBtn.disabled = false;
            } else {
                zimovStatus.textContent = "Sequence Running...";
                setTimeout(() => { 
                    zimovStatus.textContent = ""; 
                    healBtn.disabled = false;
                }, 5000);
            }
        });
    });

    // Sell Button
    const sellBtn = document.getElementById("sell-btn");
    
    sellBtn.addEventListener("click", () => {
        sellBtn.disabled = true;
        zimovStatus.textContent = "Initiating Sell Sequence...";
        zimovStatus.className = "tp-status-msg tp-ok";

        fetch("/api/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({type: "kakeula_sell"})
        }).then(r => r.json()).then(data => {
            if (data.status === "error") {
                zimovStatus.textContent = data.message;
                zimovStatus.className = "tp-status-msg tp-error";
                sellBtn.disabled = false;
            } else {
                zimovStatus.textContent = "Sequence Running...";
                setTimeout(() => { 
                    zimovStatus.textContent = ""; 
                    sellBtn.disabled = false;
                }, 5000);
            }
        });
    });

    // Auto Zimov Button
    const autoZimovBtn = document.getElementById("auto-zimov-btn");
    
    // Auto Nemesis Button
    const autoNemesisBtn = document.getElementById("auto-nemesis-btn");
    
    autoZimovBtn.addEventListener("click", () => {
        if (autoZimovBtn.classList.contains("stop")) {
            sendAction({type: "stop_auto_zimov"});
        } else {
            sendAction({type: "start_auto_zimov"});
        }
    });

    autoNemesisBtn.addEventListener("click", () => {
        if (autoNemesisBtn.classList.contains("stop")) {
            sendAction({type: "stop_auto_nemesis"});
        } else {
            sendAction({type: "start_auto_nemesis"});
        }
    });

    // --- Renderers ---
    function updateControls(state) {
        modeBtns.forEach(btn => {
            if(btn.dataset.mode === state.mode) btn.classList.add("active");
            else btn.classList.remove("active");
        });

        document.getElementById("player-hp").textContent = state.player_hp || 0;
        document.getElementById("player-mp").textContent = state.player_mp || 0;
        document.getElementById("player-max-hp").textContent = state.player_max_hp || 0;
        document.getElementById("player-max-mp").textContent = state.player_max_mp || 0;

        if(state.paused) {
            pauseBtn.classList.add("active-pause");
            pauseBtn.textContent = "RESUME NAV";
        } else {
            pauseBtn.classList.remove("active-pause");
            pauseBtn.textContent = "PAUSE NAV";
        }

        // Only enable Zimov button if map is 3e1c (Dierolt)
        if (state.current_map_hex === "3e1c") {
            zimovBtn.disabled = false;
            if (!state.auto_zimov_running) autoZimovBtn.disabled = false;
        } else {
            zimovBtn.disabled = true;
            if (!state.auto_zimov_running) autoZimovBtn.disabled = true;
        }

        // Handle auto zimov loop state
        if (state.auto_zimov_running) {
            autoZimovBtn.classList.add("stop");
            autoZimovBtn.classList.remove("primary");
            autoZimovBtn.textContent = "STOP ZIMOV LOOP";
            autoZimovBtn.disabled = false;
        } else {
            autoZimovBtn.classList.remove("stop");
            autoZimovBtn.classList.add("primary");
            autoZimovBtn.textContent = "AUTO ZIMOV LOOP";
        }
        
        if (state.auto_nemesis_running) {
            autoNemesisBtn.classList.add("stop");
            autoNemesisBtn.classList.remove("primary");
            autoNemesisBtn.textContent = "STOP NEMESIS LOOP";
            autoNemesisBtn.disabled = false;
        } else {
            autoNemesisBtn.classList.remove("stop");
            autoNemesisBtn.classList.add("primary");
            autoNemesisBtn.textContent = "AUTO NEMESIS LOOP";
            autoNemesisBtn.disabled = false; // Always enabled unless sequence is running
        }    
        healBtn.disabled = false;
        sellBtn.disabled = false;
    }

    let radarCanvas = document.getElementById("radar-canvas");
    let radarCtx = radarCanvas.getContext("2d");
    let selectedRadarTarget = null;
    let currentRadarState = { player: {x:0, y:0}, mobs: [] };
    let radarScale = 5.0; // Default zoom level
    
    // Zoom listener for radar
    radarCanvas.addEventListener("wheel", (e) => {
        e.preventDefault();
        // zoom speed
        const zoomIntensity = 0.1;
        if (e.deltaY < 0) {
            radarScale *= (1 + zoomIntensity);
        } else {
            radarScale /= (1 + zoomIntensity);
        }
        
        // Clamp scale
        if (radarScale < 0.5) radarScale = 0.5;
        if (radarScale > 20.0) radarScale = 20.0;
        
        drawRadar();
    }, {passive: false});

    document.getElementById("zoom-in-btn").addEventListener("click", () => {
        radarScale *= 1.2;
        if (radarScale > 20.0) radarScale = 20.0;
        drawRadar();
    });

    document.getElementById("zoom-out-btn").addEventListener("click", () => {
        radarScale /= 1.2;
        if (radarScale < 0.5) radarScale = 0.5;
        drawRadar();
    });

    function fetchRadar() {
        if(!isConnected) return;
        fetch("/api/radar")
            .then(r => r.json())
            .then(data => {
                currentRadarState = data;
                drawRadar();
                updateNearbyPlayers();
                updateActionPanel();
            }).catch(e => {});
    }
    
    function updateNearbyPlayers() {
        const nearbyList = document.getElementById("nearby-players-list");
        if (!nearbyList) return;
        
        const players = currentRadarState.mobs.filter(m => m.is_player);
        if (players.length === 0) {
            nearbyList.innerHTML = `<div class="inv-empty">No players nearby...</div>`;
            return;
        }
        
        nearbyList.innerHTML = "";
        players.forEach(p => {
            const row = document.createElement("div");
            row.className = "inv-row";
            row.style.alignItems = "center";
            row.innerHTML = `
                <div class="inv-info">
                    <span class="inv-name" style="color: #00f0ff;">${p.name}</span>
                    <span class="inv-id">Dist: ${p.distance}u</span>
                </div>
                <button class="sys-btn accent-b" style="padding: 4px 8px; font-size: 0.8em;" onclick="invitePlayer('${p.uid}')">INVITE</button>
            `;
            nearbyList.appendChild(row);
        });
    }

    window.invitePlayer = function(uid) {
        fetch("/api/party/invite", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({uid: uid})
        });
    };
    
    // Poll radar 2 times a second
    setInterval(fetchRadar, 500);

    function drawRadar() {
        if(!radarCanvas || !radarCtx) return;
        const rect = radarCanvas.getBoundingClientRect();
        // Adjust canvas resolution
        radarCanvas.width = rect.width;
        radarCanvas.height = rect.height;
        
        const w = radarCanvas.width;
        const h = radarCanvas.height;
        
        radarCtx.clearRect(0, 0, w, h);
        
        // Draw grid
        radarCtx.strokeStyle = "rgba(0, 240, 255, 0.2)";
        radarCtx.beginPath();
        for(let i=0; i<w; i+=40) { radarCtx.moveTo(i, 0); radarCtx.lineTo(i, h); }
        for(let i=0; i<h; i+=40) { radarCtx.moveTo(0, i); radarCtx.lineTo(w, i); }
        radarCtx.stroke();
        
        const px = currentRadarState.player.x;
        const py = currentRadarState.player.y;
        
        const cx = w / 2;
        const cy = h / 2;
        
        // Use the global radarScale
        const scale = radarScale; // zoom level: pixels per game unit
        
        // Draw Player
        radarCtx.fillStyle = "#00ff00";
        radarCtx.beginPath();
        radarCtx.arc(cx, cy, 5, 0, Math.PI*2);
        radarCtx.fill();
        radarCtx.shadowBlur = 10;
        radarCtx.shadowColor = "#00ff00";
        radarCtx.fillText("YOU", cx - 10, cy - 10);
        radarCtx.shadowBlur = 0;
        
        // Draw Mobs
        currentRadarState.mobs.forEach(m => {
            const dx = (m.x - px) * scale;
            const dy = (m.y - py) * scale; // standard cartesian
            const drawX = cx + dx;
            const drawY = cy + dy;
            
            // Check if selected
            if (selectedRadarTarget === m.uid) {
                radarCtx.strokeStyle = "#ff00ff";
                radarCtx.lineWidth = 2;
                radarCtx.beginPath();
                radarCtx.arc(drawX, drawY, 8, 0, Math.PI*2);
                radarCtx.stroke();
            }
            
            radarCtx.fillStyle = m.is_player ? "#00f0ff" : "#ff0044";
            radarCtx.beginPath();
            radarCtx.arc(drawX, drawY, 4, 0, Math.PI*2);
            radarCtx.fill();
            
            radarCtx.fillStyle = "#fff";
            radarCtx.font = "10px sans-serif";
            radarCtx.fillText(`${m.name}`, drawX + 6, drawY - 4);
        });
    }
    
    // Canvas Click Handler
    radarCanvas.addEventListener("click", (e) => {
        const rect = radarCanvas.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const clickY = e.clientY - rect.top;
        
        const px = currentRadarState.player.x;
        const py = currentRadarState.player.y;
        const cx = radarCanvas.width / 2;
        const cy = radarCanvas.height / 2;
        const scale = radarScale;
        
        let found = null;
        for (let m of currentRadarState.mobs) {
            const dx = (m.x - px) * scale;
            const dy = (m.y - py) * scale;
            const mx = cx + dx;
            const my = cy + dy;
            
            const distToClick = Math.sqrt((clickX - mx)**2 + (clickY - my)**2);
            if (distToClick < 15) { // 15 pixel click radius
                found = m;
                break;
            }
        }
        
        if (found) {
            selectedRadarTarget = found.uid;
        } else {
            selectedRadarTarget = null;
        }
        drawRadar();
        updateActionPanel();
    });

    const actionPanel = document.getElementById("target-action-panel");
    const tgtNameSpan = document.getElementById("target-name");
    const tgtDistSpan = document.getElementById("target-dist");
    
    function updateActionPanel() {
        if (!selectedRadarTarget) {
            actionPanel.style.display = "none";
            return;
        }
        
        const m = currentRadarState.mobs.find(m => m.uid === selectedRadarTarget);
        if (!m) return;
        
        actionPanel.style.display = "block";
        tgtNameSpan.textContent = m.name;
        tgtDistSpan.textContent = `Distance: ${m.distance}u`;
    }
    
    document.getElementById("cast-nemesis-btn").addEventListener("click", () => {
        if(!selectedRadarTarget) return;
        fetch("/api/cast_skill", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({uid: selectedRadarTarget, skill_hex: "138f"}) // Nemesis ID
        });
        selectedRadarTarget = null;
        updateActionPanel();
        drawRadar();
    });
    
    document.getElementById("party-invite-btn").addEventListener("click", () => {
        if(!selectedRadarTarget) return;
        fetch("/api/party/invite", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({uid: selectedRadarTarget})
        });
        selectedRadarTarget = null;
        updateActionPanel();
        drawRadar();
    });
    
    document.getElementById("radar-auto-nemesis-btn").addEventListener("click", () => {
        if(!selectedRadarTarget) return;
        
        const m = currentRadarState.mobs.find(m => m.uid === selectedRadarTarget);
        if (!m) return;
        
        fetch("/api/auto_nemesis/start", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ target_name: m.name, target_id: m.id })
        });
        
        // Don't clear target so user can see it running
    });
    
    document.getElementById("radar-stop-nemesis-btn").addEventListener("click", () => {
        fetch("/api/auto_nemesis/stop", {
            method: "POST"
        });
    });
    
    document.getElementById("accept-invite-btn").addEventListener("click", () => {
        fetch("/api/party/accept", {
            method: "POST",
            headers: {"Content-Type": "application/json"}
        }).then(r => r.json()).then(data => {
            if (data.error) console.error(data.error);
        }).catch(e => console.error(e));
    });

    document.getElementById("party-leave-btn").addEventListener("click", () => {
        fetch("/api/party/leave", {
            method: "POST",
            headers: {"Content-Type": "application/json"}
        }).then(r => r.json()).then(data => {
            if (data.error) console.error(data.error);
        }).catch(e => console.error(e));
    });
    
    if (document.getElementById("buffs-btn")) {
        document.getElementById("buffs-btn").addEventListener("click", () => {
            sendAction({type: "cast_buffs"});
        });
    }
    
    // Individual Buffs
    const individualBuffs = {
        "buff-rev-btn": "revelation",
        "buff-risp-btn": "risparmio",
        "buff-pre-btn": "preire",
        "buff-bless-btn": "bless"
    };
    
    for (const [btnId, buffId] of Object.entries(individualBuffs)) {
        const btn = document.getElementById(btnId);
        if (btn) {
            btn.addEventListener("click", () => {
                sendAction({type: "cast_individual_buff", buff_id: buffId});
            });
        }
    }

    function updateParty(state) {
        const inviteAlert = document.getElementById("party-invite-alert");
        if (state.pendingInvite) {
            inviteAlert.style.display = "block";
        } else {
            inviteAlert.style.display = "none";
        }

        const membersList = document.getElementById("party-members-list");
        if (!state.party || Object.keys(state.party).length === 0) {
            membersList.innerHTML = `<div class="inv-empty">Not in a party...</div>`;
            return;
        }

        membersList.innerHTML = "";
        Object.values(state.party).forEach(member => {
            const row = document.createElement("div");
            row.className = "inv-row";
            row.innerHTML = `
                <div class="inv-info">
                    <span class="inv-name">Member UID: ${member.uid}</span>
                </div>
            `;
            membersList.appendChild(row);
        });
    }

    function updateRadar(state) {
        // Obsolete, replaced by fetchRadar API
    }

    document.getElementById("set-coord-btn")?.addEventListener("click", () => {
        const x = document.getElementById("set-coord-x").value;
        const y = document.getElementById("set-coord-y").value;
        if (!x || !y) return;
        
        fetch("/api/set_coords", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({x: parseFloat(x), y: parseFloat(y)})
        });
    });

    function updateInventory(state) {
        const spinaEl = document.getElementById("spina-earned");
        if(spinaEl) spinaEl.textContent = state.spina_earned ? state.spina_earned.toLocaleString() : "0";

        const items = state.inventory;
        if(!items || Object.keys(items).length === 0) {
            inventoryList.innerHTML = `<div class="inv-empty">No items loaded...</div>`;
            return;
        }

        // Sort by count descending
        const sorted = Object.entries(items).sort((a, b) => b[1].count - a[1].count);

        inventoryList.innerHTML = "";
        sorted.forEach(([hex, item]) => {
            const row = document.createElement("div");
            row.className = "inv-row";
            row.innerHTML = `
                <div class="inv-info">
                    <span class="inv-name">${item.name}</span>
                    <span class="inv-id">${hex}</span>
                </div>
                <span class="inv-count">x${item.count}</span>
            `;
            inventoryList.appendChild(row);
        });
    }

    // --- Auto-Resume on Page Load ---
    fetch("/api/state")
    .then(r => r.json())
    .then(data => {
        if(data.connected) {
            console.log("Already connected. Auto-resuming dashboard.");
            statusMsg.textContent = "Session restored.";
            pollInterval = setInterval(fetchState, 500); 
            transitionToDashboard();
            fetchState();
        }
    })
    .catch(err => console.log("No active session found."));
    
});
