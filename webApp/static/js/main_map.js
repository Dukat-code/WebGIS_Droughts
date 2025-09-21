class Map {
    map;

    constructor(cfg, name) {
        // Initialize map
        console.log("Map config:", cfg);
        this.layers = {};
        this.activeDate = null;
        this.map = L.map(name, {
            zoomControl: true,
            scrollWheelZoom: true,
            dragging: true,
            doubleClickZoom: true,
            boxZoom: true,
            keyboard: true,
            attributionControl: false,
            minZoom: cfg.min_zoom,   // minimum zoom level
            maxZoom: cfg.max_zoom    // maximum zoom level
        }).setView([cfg.center_lat, cfg.center_lon], cfg.initial_zoom);

        // Base map
        const tiles = L.tileLayer(cfg.base_map_url, {
        }).addTo(this.map);

        // Time slider for time series layers
        const availableDates = [
                "1991-01-01",
                "1991-06-01",
                "2001-01-01",
                "2001-06-01",
                "2011-01-01",
                "2011-06-01",
                "2020-01-01",
                "2011-06-01",
                "2025-01-01",
                "2025-06-01"
            ];

        this.timeline = new TimelineWidget({
            map: this.map,
            parent: this,
            dates: availableDates
        });
        
        // Add layers
        for (const layerName in cfg.layers) {
            this.addLayer(
                layerName,
                cfg.layers[layerName].url,
                cfg.layers[layerName].active === 'true',
                cfg.layers[layerName].opacity,
                cfg.layers[layerName].tms === 'true',
                cfg.layers[layerName].time === 'true',
                cfg.layers[layerName].dateformat || 'yyyy-mm-dd'
            )
        }

        // Layer control widget
        const layersByTopic = {
            precipitation: {
                "Layer 1": { 
                    active: true, 
                    opacity: 1, 
                    layerObj: this.layers["era5_ecowas"]
                },
                "Layer 2": { 
                    active: false, 
                    opacity: 0.5, 
                    layerObj: this.layers["era5_ecowas_2025_notime"] 
                }
            },
            temperature: {
                "Layer 1": { 
                    active: true, 
                    opacity: 1, 
                    layerObj: this.layers["era5_ecowas"]
                },
            }
        };

        new LayerWidget(
                    { 
                        id: "layer-widget", 
                        title: "Layers", 
                        position: { top: "24px", left: "24px" },
                        map: this.map,
                        parent: this,
                        timeline: this.timeline
                    }, 
                    layersByTopic
                );

        // Feature info control
        this.setFeatureInfoControl();

        
    }

    setFeatureInfoControl() {
        // feature info
        this.infoActive = false;
        const infoControl = L.control({position: 'topright'});

        infoControl.onAdd = (map) => {
            const div = L.DomUtil.create('div', 'info-toggle-control');
            div.innerHTML = `<button id="info-toggle-btn" title="Toggle Info Service" style="
                background: #888;
                color: #fff;
                border: none;
                border-radius: 4px;
                font-size: 1.2em;
                padding: 8px 12px;
                cursor: pointer;
                box-shadow: 0 2px 8px rgba(44,62,80,0.08);
            ">
                &#9432;             
            </button>`;
            // Prevent map interactions when clicking the button
            L.DomEvent.disableClickPropagation(div);
            return div;
        };

        infoControl.addTo(this.map);

        // Add event listener for the button
        setTimeout(() => {
            const btn = document.getElementById('info-toggle-btn');
            if (btn) {
                btn.onclick = () => {
                    // Check if there are any layers on the map
                    const hasAnyLayer = Object.values(this.layers).some(layer => this.map.hasLayer(layer) && layer.timeseries);
                    if (!hasAnyLayer) return;
                    this.infoActive = !this.infoActive;
                    btn.style.background = this.infoActive ? "#2b3e50" : "#888";
                    // Change map cursor
                    const mapDiv = document.getElementById('map');
                    if (mapDiv) {
                        mapDiv.style.cursor = this.infoActive ? "crosshair" : "";
                    }
                };
            }
        }, 100);
        this.map.on('click', (e) => {
            if(!this.infoActive) return;
            // Get clicked coordinates
            const latlng = e.latlng;
            // Call your info function
            this.getFeatureInfo(latlng);
        });
    }

    addLayer(name, url, active, opacity, tms, time, dateFormat='yyyy-mm-dd') {
        const layer = L.tileLayer(url, {
            opacity: opacity,
            tms: tms
        });
        layer.timeseries = time;
        if(time){
            layer.dateFormat = dateFormat
        }

        if (active) {
            layer.addTo(this.map);
            this.timeline.setActiveLayer(layer);
        }

        this.layers[name] = layer;
    }

    getFeatureInfo(latlng) {
        const lat = latlng.lat.toFixed(4);
        const lon = latlng.lng.toFixed(4);
        const date = this.activeDate;
        const activeLayer = Object.keys(this.layers).find(layerName => this.map.hasLayer(this.layers[layerName]) && this.layers[layerName].timeseries);
        console.log(`Fetching info for ${activeLayer} at (${lat}, ${lon}) on ${date}`);
        if(!activeLayer) {
            alert('No active time series layer selected.');
            return;
        }
        fetch(`/get_feature_info/${activeLayer}/${lat}/${lon}/${date}`)
            .then(response => response.json())
            .then(data => {
                // Display the feature info (customize as needed)
                let info = `Info for ${activeLayer} at (${lat}, ${lon}) on ${date}:\n`;
                // Extract the value from the response (adjust as needed)
                const value = data.value || 'No value found';

                // Create popup content with value and link
                const popupContent = `
                    <div>
                        ${info}<br>
                        <strong>Value:</strong> ${value}<br>
                        <button id="modal-open-btn" title="Open in Modal">Open chart</button>
                    </div>
                `;

                // Open popup at the clicked location
                L.popup()
                    .setLatLng(latlng)
                    .setContent(popupContent)
                    .openOn(this.map);
                
                // Add event listener to the button after the popup is rendered
                setTimeout(() => {
                    let title = `Data for ${activeLayer} at (${lat}, ${lon})`;
                    const btn = document.getElementById('modal-open-btn');
                    if (btn) {
                        btn.onclick = () => {
                            this.openModal(title, `http://localhost:5000/clim_chart/${activeLayer}/${lat}/${lon}/1991/2024`);
                        };
                    }
                }, 100);
            })
            .catch(error => {
                console.error('Error fetching feature info:', error);
            });
        
    }

    openModal(title, url) {
    const modal = new ModalWidget({
        title: title,
        content: `<iframe src="${url}" style="width:100%;height:100%;border:none;"></iframe>`
    });
    modal.open();
}
}

class Widget {
    constructor(options) {
        this.id = options.id || `widget-${Math.random().toString(36).substr(2, 9)}`;
        this.title = options.title || 'Widget';
        this.position = options.position || { top: '24px', left: '24px' };
        this.content = options.content || '';
        this.createWidget();
    }

    createWidget() {
        // Create widget container
        this.container = document.createElement('div');
        this.container.className = 'widget';
        this.container.id = this.id;
        this.container.style.position = 'absolute';
        this.container.style.top = this.position.top;
        this.container.style.left = this.position.left;

        // Header
        this.header = document.createElement('div');
        this.header.className = 'widget-header';
        this.header.innerHTML = `<span>${this.title}</span><span class="widget-toggle">&#9660;</span>`;
        this.header.onclick = () => this.toggle();

        // Content
        this.contentDiv = document.createElement('div');
        this.contentDiv.className = 'widget-content';
        this.contentDiv.innerHTML = this.content;

        this.container.appendChild(this.header);
        this.container.appendChild(this.contentDiv);

        document.getElementById('map-container').appendChild(this.container);
    }

    toggle() {
        this.container.classList.toggle('open');
    }

    setContent(html) {
        this.contentDiv.innerHTML = html;
    }
}

class LayerWidget extends Widget {
    constructor(options, layersByTopic) {
        super(options);
        this.map = options.map;
        this.parent = options.parent;
        this.timeline = options.timeline;
        this.layersByTopic = layersByTopic; // { topic: { layerName: {active, opacity, layerObj} } }
        this.topics = Object.keys(layersByTopic);
        this.selectedTopic = this.topics[0];
        this.renderTopicDropdown();
        this.renderLayerControls();
    }

    renderTopicDropdown() {
        const dropdown = document.createElement('select');
        dropdown.className = 'topic-dropdown';
        this.topics.forEach(topic => {
            const option = document.createElement('option');
            option.value = topic;
            option.textContent = topic.charAt(0).toUpperCase() + topic.slice(1);
            dropdown.appendChild(option);
        });
        dropdown.value = this.selectedTopic;
        dropdown.onchange = (e) => {
            this.selectedTopic = e.target.value;
            this.renderLayerControls();
        };
        // Insert dropdown at the top of widget content
        this.setContent('');
        this.contentDiv.appendChild(dropdown);
    }

    renderLayerControls() {
        // Remove previous controls except dropdown
        while (this.contentDiv.children.length > 1) {
            this.contentDiv.removeChild(this.contentDiv.lastChild);
        }
        const layers = this.layersByTopic[this.selectedTopic];
        for (const layerName in layers) {
            const layer = layers[layerName];
            const wrapper = document.createElement('div');
            wrapper.className = 'layer-control-row';

            // First line: checkbox + label
            const line1 = document.createElement('div');
            line1.style.display = 'flex';
            line1.style.alignItems = 'center';
            line1.style.gap = '8px';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = layer.active;
            checkbox.setAttribute('data-layer', layerName);
            checkbox.onchange = (e) => {
                if (e.target.checked) {
                    // Uncheck all other checkboxes and remove their layers
                    this.contentDiv.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                        if (cb !== e.target) {
                            cb.checked = false;
                            const otherLayerName = cb.getAttribute('data-layer');
                            const otherLayer = layers[otherLayerName];
                            if (otherLayer && otherLayer.layerObj) {
                                this.removeLayer(otherLayer.layerObj);
                            }
                        }
                    });
                    // Add the selected layer
                    if (layer.layerObj) {
                        console.log(layer.layerObj);
                        layer.layerObj.addTo(this.map);
                        if(layer.layerObj.timeseries){
                            this.timeline.setActiveLayer(layer.layerObj);
                        } else {   
                            this.timeline.setActiveLayer(null);
                        }
                    }
                } else {
                    // Remove the layer if unchecked
                    if (layer.layerObj) {
                        this.removeLayer(layer.layerObj);
                        if(layer.layerObj.timeseries){
                            this.timeline.setActiveLayer(null);
                        }
                    }
                }
            };

            const label = document.createElement('label');
            label.textContent = layerName;
            label.style.marginRight = '8px';

            line1.appendChild(checkbox);
            line1.appendChild(label);

            // Second line: slider
            const line2 = document.createElement('div');
            line2.style.width = '100%';
            line2.style.marginTop = '4px';

            const slider = document.createElement('input');
            slider.type = 'range';
            slider.min = 0;
            slider.max = 1;
            slider.step = 0.01;
            slider.value = layer.opacity;
            slider.setAttribute('data-layer-opacity', layerName);
            slider.className = 'layer-slider';
            slider.oninput = (e) => {
                if (layer.layerObj) {
                    layer.layerObj.setOpacity(parseFloat(e.target.value));
                }
            };

            line2.appendChild(slider);

            wrapper.appendChild(line1);
            wrapper.appendChild(line2);

            this.contentDiv.appendChild(wrapper);
        }
    }

    removeLayer(layer) {
        const btn = document.getElementById('info-toggle-btn');
        if (btn && this.parent.infoActive) {
            btn.click(); // Deactivate info mode if active
        }
        this.map.removeLayer(layer);
        this.parent.activeDate = null;
    }
}

class TimelineWidget extends Widget {
    constructor(options) {
        options.id = options.id || 'timeline-widget';
        options.title = options.title || '';
        super(options);

        this.map = options.map;
        this.parent = options.parent;
        this.dates = options.dates || []; // Array of date strings
        this.parent.activeDate = this.dates.length > 0 ? this.dates[0] : null;
        this.currentIndex = 0;
        this.isPlaying = false;
        this.interval = null;

        this.activeLayer = null;
        this.dateFormat = options.dateFormat || 'yyyy-mm-dd';

        this.renderTimeline();
        this.setWidgetStyle();
    }

    setWidgetStyle() {
        this.container.style.position = 'absolute';
        this.container.style.left = '0';
        this.container.style.bottom = '0';
        this.container.style.width = '100%';
        this.container.style.borderRadius = '0';
        this.container.style.zIndex = '20';
        this.container.style.boxShadow = '0 -2px 8px rgba(44,62,80,0.08)';
        this.container.style.maxHeight = '10vh';
        this.container.style.overflow = 'hidden';
        this.container.id = 'timeline-widget';
    }

    renderTimeline() {
        this.setContent('');

        const controls = document.createElement('div');
        controls.className = 'timeline-controls';

        this.playPauseBtn = document.createElement('button');
        this.playPauseBtn.className = 'timeline-btn';
        this.playPauseBtn.innerHTML = '<span class="material-icons">&#9654;</span>';
        this.playPauseBtn.onclick = () => this.togglePlayPause();

        this.reloadBtn = document.createElement('button');
        this.reloadBtn.className = 'timeline-btn';
        this.reloadBtn.innerHTML = '<span class="material-icons">&#8634;</span>';
        this.reloadBtn.onclick = () => this.reloadTimeline();

        this.slider = document.createElement('input');
        this.slider.type = 'range';
        this.slider.min = 0;
        this.slider.max = this.dates.length > 0 ? this.dates.length - 1 : 0;
        this.slider.value = this.currentIndex;
        this.slider.className = 'timeline-slider';
        this.slider.oninput = () => this.updateElements();

        this.dateLabel = document.createElement('span');
        this.dateLabel.className = 'timeline-date-label';
        this.dateLabel.textContent = this.dates[this.currentIndex] || '';

        controls.appendChild(this.playPauseBtn);
        controls.appendChild(this.reloadBtn);
        controls.appendChild(this.slider);
        controls.appendChild(this.dateLabel);

        this.contentDiv.appendChild(controls);
    }

    togglePlayPause() {
        if (this.isPlaying) {
            this.pause();
        } else {
            this.play();
        }
    }

    play() {
        this.isPlaying = true;
        this.playPauseBtn.innerHTML = '<span class="material-icons">&#10073;&#10073;</span>';
        this.interval = setInterval(() => {
            if (this.currentIndex < this.dates.length - 1) {
                this.currentIndex++;
                this.slider.value = this.currentIndex;
                this.updateElements();
            } else {
                this.pause();
            }
        }, 500);
    }

    pause() {
        this.isPlaying = false;
        this.playPauseBtn.innerHTML = '<span class="material-icons">&#9654;</span>';
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
    }

    reloadTimeline() {
        this.pause();
        this.currentIndex = 0;
        this.slider.value = this.currentIndex;
        this.updateElements();
    }

    updateElements() {
        this.parent.activeDate = this.dates[this.currentIndex];
        this.updateDateLabel();
        this.updateLayer();
    }

    updateLayer() {
        const date = this.dates[this.currentIndex];
        this.parent.activeDate = date;
        const layer = this.activeLayer
        console.log("Updating layer for date:", this.dates[this.currentIndex]);
        if (this.map.hasLayer(layer) && 
            layer.timeseries) {
                const baseUrl = layer._url;
                // Update the TIME parameter in the URL and refresh the layer
                const newUrl = baseUrl.replace(/TIME=[^&]*/, `TIME=${date}`);
                this.map.removeLayer(layer);
                layer.setUrl(newUrl);
                this.map.addLayer(layer);
            }
    }

    updateDateLabel() {
        this.currentIndex = parseInt(this.slider.value);
        let dateStr = this.dates[this.currentIndex] || '';
        if (this.dateFormat === 'yyyy-mm') {
            dateStr = dateStr.slice(0, 7); // Keep only yyyy-mm
        }
        this.dateLabel.textContent = dateStr;
    }

    setActiveLayer(layer) {
        this.activeLayer = layer;      
        if(layer===null)
            this.hide();
        else{
            this.setDateFormat(layer.dateFormat);
            if(this.hidden){
                this.show();
            }
        }
    }

    setDateFormat(format) {
        this.dateFormat = format;
        this.updateDateLabel();
    }

    show() {
        this.hidden = false;
        this.container.style.display = '';
        // Resize the map to leave space for the timeline widget
        const mapDiv = document.getElementById('map');
        if (mapDiv) {
            mapDiv.style.height = 'calc(100% - 20vh)';
            if (this.map && this.map.invalidateSize) {
                this.map.invalidateSize();
            }
        }
    }

    hide() {
        this.hidden = true;
        this.container.style.display = 'none';
        // Resize the map to take all available space
        const mapDiv = document.getElementById('map');
        if (mapDiv) {
            mapDiv.style.height = '100%';
            if (this.map && this.map.invalidateSize) {
                this.map.invalidateSize();
            }
        }
    }
}

class ModalWidget {
    constructor(options) {
        this.id = options.id || `modal-${Math.random().toString(36).substr(2, 9)}`;
        this.title = options.title || '';
        this.content = options.content || '';
        this.createModal();
    }

    createModal() {
        // Overlay
        this.overlay = document.createElement('div');
        this.overlay.className = 'modal-overlay';
        this.overlay.id = `${this.id}-overlay`;

        // Modal container
        this.container = document.createElement('div');
        this.container.className = 'modal-container';
        this.container.id = this.id;

        // Header with close button
        const header = document.createElement('div');
        header.className = 'modal-header';
        header.innerHTML = `
            <span class="modal-title">${this.title}</span>
            <button class="modal-close-btn" title="Close">&times;</button>
        `;
        header.querySelector('.modal-close-btn').onclick = () => this.close();

        // Content
        const contentDiv = document.createElement('div');
        contentDiv.className = 'modal-content';
        contentDiv.innerHTML = this.content;

        this.container.appendChild(header);
        this.container.appendChild(contentDiv);
        this.overlay.appendChild(this.container);

        document.body.appendChild(this.overlay);
    }

    open() {
        this.overlay.style.display = 'flex';
    }

    close() {
        this.overlay.style.display = 'none';
    }
}