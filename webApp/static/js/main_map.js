/**
 * main_map.js
 * 
 * JavaScript code to initialize and manage the interactive map,
 * including layers, timeline, and widgets.
 */

/**
 * Map class to handle map initialization and layer management
 */
class Map {
    map;

    constructor(cfg, name) {
        // Initialize map
        this.localhost = cfg.localhost;
        this.layers = {};
        this.activeDate = null;
        this.map = L.map(name, {
            zoomControl: false,
            scrollWheelZoom: true,
            dragging: true,
            doubleClickZoom: true,
            boxZoom: true,
            keyboard: true,
            attributionControl: false,
            minZoom: cfg.min_zoom,   // minimum zoom level
            maxZoom: cfg.max_zoom    // maximum zoom level
        }).setView([cfg.center_lat, cfg.center_lon], cfg.initial_zoom);
        
        // Custom zoom control (styled like info/download widgets, top right)
        this.addCustomZoomControl();

        // Base map
        const tiles = L.tileLayer(cfg.base_map_url, {
        }).addTo(this.map);


        // Time slider for time series layers
        const availableDates = [];

        this.timeline = new TimelineWidget({
            title: "Time Line",
            map: this.map,
            parent: this,
            dates: availableDates
        });
        
        // Add layers
        console.log("Adding layers from config:", cfg.layers);
         for (const layerName in cfg.layers) {
            this.addLayer(
                layerName,
                cfg.layers[layerName].title,
                cfg.layers[layerName].url,
                cfg.layers[layerName].get_feature_info_url ? cfg.layers[layerName].get_feature_info_url : cfg.get_feature_info_url,
                cfg.layers[layerName].legend || '',
                cfg.layers[layerName].info || '',
                cfg.layers[layerName].topic,
                cfg.layers[layerName].active === 'true',
                cfg.layers[layerName].opacity,
                cfg.layers[layerName].tms === 'true',
                cfg.layers[layerName].time === 'true',
                cfg.layers[layerName].min_date,
                cfg.layers[layerName].max_date,
                cfg.layers[layerName].date_format || 'yyyy-mm'
            )
        }

        // Layer control widget
        const layersByTopic = this.createLayersByTopic(cfg);

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

        // Download widget
        this.downloadWidget = new DownloadWidget({
            map: this.map,
            parent: this
        });

        // Download control
        this.setDownloadControl();

    }

    /**
     * Add a custom zoom control styled like info/download widgets, top right above info button
     */
    addCustomZoomControl() {
        const zoomControl = L.control({ position: 'topright' });
        zoomControl.onAdd = (map) => {
            const container = L.DomUtil.create('div', 'custom-zoom-control');
            container.style.display = 'flex';
            container.style.flexDirection = 'column';
            container.style.alignItems = 'center';
            container.style.marginBottom = '18px';
            // Zoom in button
            const zoomInBtn = document.createElement('button');
            zoomInBtn.id = 'custom-zoom-in-btn';
            zoomInBtn.innerHTML = '+';
            zoomInBtn.title = 'Zoom in';
            // Zoom out button
            const zoomOutBtn = document.createElement('button');
            zoomOutBtn.id = 'custom-zoom-out-btn';
            zoomOutBtn.innerHTML = '-';
            zoomOutBtn.title = 'Zoom out';
            // Add event listeners
            zoomInBtn.onclick = (e) => {
                e.preventDefault();
                this.map.zoomIn();
            };
            zoomOutBtn.onclick = (e) => {
                e.preventDefault();
                this.map.zoomOut();
            };
            // Prevent map drag when clicking
            L.DomEvent.disableClickPropagation(container);
            container.appendChild(zoomInBtn);
            container.appendChild(zoomOutBtn);
            return container;
        };
        zoomControl.addTo(this.map);
    }

    /**
     * Create a mapping of layers by their topic
     * @param {*} cfg 
     * @returns {Object} layersByTopic - { topic: { layerName: {active, opacity, layerObj} }}
     */
    createLayersByTopic(cfg) {
        const layersByTopic = {};
        for (const layerName in cfg.layers) {
            const layerCfg = cfg.layers[layerName];
            const topic = layerCfg.topic || 'other';
            if (!layersByTopic[topic]) layersByTopic[topic] = {};
            layersByTopic[topic][layerName] = {
                active: layerCfg.active === 'true',
                opacity: layerCfg.opacity,
                layerObj: this.layers[layerName]
            };
        }
        return layersByTopic;
    }

    /**
     * Set up the feature info control (info button and click handler)
     */
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
                    const hasAnyLayer = Object.values(this.layers).some(layer => this.map.hasLayer(layer) && 
                                                                        (layer.timeseries || layer.topic==='facilities'));
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

    /**
     *  Set up the download control (download button and widget toggle)
     */
    setDownloadControl() {
        if(!window.isLoggedIn) return;
        this.downloadActive = false;
        const downloadControl = L.control({position: 'topright'});
        downloadControl.onAdd = (map) => {
            const div = L.DomUtil.create('div', 'download-toggle-control');
            div.innerHTML = `<button id="download-toggle-btn" title="Toggle Download Widget" style="
                background: #888;
                color: #fff;
                border: none;
                border-radius: 4px;
                font-size: 1.2em;
                padding: 8px 12px;
                cursor: pointer;
                box-shadow: 0 2px 8px rgba(44,62,80,0.08);
            ">
                <span class="material-icons">&#8595;</span>
            </button>`;
            L.DomEvent.disableClickPropagation(div);
            return div;
        };

        downloadControl.addTo(this.map);

        setTimeout(() => {
            const btn = document.getElementById('download-toggle-btn');
            if (btn) {
                btn.onclick = () => {
                    // Check if there are any layers on the map
                    const hasAnyLayer = Object.values(this.layers).some(layer => this.map.hasLayer(layer) && layer.timeseries);
                    if (!hasAnyLayer) return;
                    this.downloadActive = !this.downloadActive;
                    btn.style.background = this.downloadActive ? "#2b3e50" : "#888";
                    if (this.downloadActive) {
                        this.downloadWidget.show();
                    } else {
                        this.downloadWidget.hide();
                    }
                };
            }
        }, 100);
    }

    /**
     * Create a new layer and add it to the collection of layers of the map
     * @param {*} name 
     * @param {*} url 
     * @param {*} getFeatureUrl 
     * @param {*} legend 
     * @param {*} info 
     * @param {*} topic 
     * @param {*} active 
     * @param {*} opacity 
     * @param {*} tms 
     * @param {*} time 
     * @param {*} initDate
     * @param {*} endDate
     * @param {*} dateFormat 
     */
    addLayer(name, title, url, getFeatureUrl, legend, info, topic, active, opacity, tms, time, initDate, endDate, dateFormat='yyyy-mm') {
        let layer;
        if(topic==='facilities'){
            // Special case for facilities: fetch GeoJSON and add as point layer
            layer = this.createJsonLayer(url);
        } else {
            // Standard tile layer
            layer = L.tileLayer(url, {
                opacity: opacity,
                tms: tms
            });
        }
        layer.title = title || name;
        layer.info = info || '';
        layer.legend = legend || '';
        layer.timeseries = time;
        layer.topic = topic || '';
        layer.getFeatureUrl = `${getFeatureUrl}/${name}`;
        if(time){
            layer.minDate = initDate || null;
            layer.maxDate = endDate || null;
            layer.dateFormat = dateFormat
        }

        if (active) {
            layer.addTo(this.map);
            if (time) {
                this.timeline.setActiveLayer(layer);
            }
        }

        this.layers[name] = layer;
    }

    /**
     * Create a GeoJSON layer
     * @param {*} url 
     * @returns 
     */
    createJsonLayer(url){
        let layer = L.geoJSON([], {
            pointToLayer: (feature, latlng) => {
                return L.circleMarker(latlng, {
                    radius: 6,
                    fillColor: "#ff7800",
                    color: "#000",
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.8
                });
            },
            onEachFeature: this.onEachFeature.bind(this)
        });
        fetch(url)
        .then(response => response.json())
        .then(data => {
            layer.addData(data);
        })
        .catch(error => {
            console.error('Error loading GeoJSON data:', error);
        });
        return layer;
    }

    /**
     * On each feature (for GeoJSON layers), bind popup and set up event listeners
     * @param {*} feature 
     * @param {*} layer 
     */
    onEachFeature(feature, layer) {
        const mapInstance = this;
        let popupContent = `<strong>${feature.properties.name || 'No name'}</strong><br>`;
        for (const prop in feature.properties) {
            if (prop !== 'name') {
                popupContent += `${prop}: ${feature.properties[prop]}<br>`;
            }
        }
        layer.bindPopup(popupContent);

        const getActiveDate = () => mapInstance.activeDate;
        const getInfoActive = () => mapInstance.infoActive;

        layer.on('popupopen', function(e) {
            if(!getInfoActive()){
                layer.closePopup();
                return;
            } 
            const lat = feature.properties.latitude;
            const lon = feature.properties.longitude;
            const activeDate = getActiveDate();
            let url = `/get_data_from_station/${lat}/${lon}`;
            if(activeDate)
                url += `/${activeDate}`;
            fetch(url)
                .then(response => response.json())
                .then(data => {
                    let extraInfo = "<hr><strong>Station Data:</strong><br>";
                    for (const key in data) {
                        extraInfo += `${key}: ${data[key]}<br>`;
                    }
                    if(Object.keys(data).length === 0){
                        extraInfo += `<em>No data available for this station on date ${activeDate}</em><br>`;
                    }
                    // Add "Open chart" button
                    extraInfo += `<button id="modal-open-btn" title="Open in Modal">Open chart</button>`;
                    layer.setPopupContent(popupContent + extraInfo);

                    // Attach event listener after popup is rendered
                    setTimeout(() => {
                        let title = `Data for Station at (${lat}, ${lon})`;
                        const btn = document.getElementById('modal-open-btn');
                        if (btn) {
                            btn.onclick = () => {
                                mapInstance.openModal(
                                    title,
                                    `${mapInstance.localhost}/clim_station_chart/meteostation_month_data/${lat}/${lon}`
                                );
                            };
                        }
                    }, 100);
                })
                .catch(error => {
                    layer.setPopupContent(popupContent + "<br><em>Error loading station data</em>");
                });
        });
    }

    /**
     * Get feature information for a specific latitude/longitude
     * @param {*} latlng 
     * @returns 
     */
    getFeatureInfo(latlng) {
        const lat = latlng.lat.toFixed(4);
        const lon = latlng.lng.toFixed(4);
        const date = this.activeDate;
        const activeLayer = Object.keys(this.layers).find(layerName => this.map.hasLayer(this.layers[layerName]) && this.layers[layerName].timeseries);
        const url = this.layers[activeLayer]?.getFeatureUrl;
        if(!activeLayer) {
            alert('No active time series layer selected.');
            return;
        }
        fetch(`${url}/${lat}/${lon}/${date}`)
            .then(response => response.json())
            .then(data => {
                // Display the feature info (customize as needed)
                let info = `Info for ${activeLayer} at (${lat}, ${lon}) on ${date}:\n`;
                // Extract the value from the response (adjust as needed)
                let value = '';
                if(data.value){
                    value = data.value;
                } else {
                    value+="<br>";
                    for(let i in data){ 
                        value += `${i}: ${data[i]} <br>`;
                    }

                }

                // Create popup content with value and link
                const popupContent = `
                    <div>
                        ${info}<br>
                        <strong>Value(s):</strong> ${value}<br>
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
                            this.openModal(title, `${this.localhost}/clim_chart/${activeLayer}/${lat}/${lon}`);
                        };
                    }
                }, 100);
            })
            .catch(error => {
                console.error('Error fetching feature info:', error);
            });
        
    }

    /**
     * Open a modal dialog with given title and URL
     * @param {*} title 
     * @param {*} url 
     */
    openModal(title, url) {
        const modal = new ModalWidget({
            title: title,
            content: `<iframe src="${url}" style="width:100%;height:100%;border:none;"></iframe>`
        });
        modal.open();
    }
}

/**
 * Base Widget class
 */
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

/**
 * Layer control widget
 */
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

            // First line: checkbox + label + legend toggle
            const line1 = document.createElement('div');
            line1.style.display = 'flex';
            line1.style.alignItems = 'center';
            line1.style.gap = '8px';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = layer.active;
            checkbox.setAttribute('data-layer', layerName);

            const label = document.createElement('label');
            console.log(`Rendering layer control for ${layerName}, title: ${layer.layerObj?.title || layerName}`);
            label.textContent = layer.layerObj?.title || layerName;
            label.style.marginRight = '8px';

            // Timeline toggle
            const timelineToggle = document.createElement('button');
            timelineToggle.textContent = 'Timeline';
            timelineToggle.className = 'legend-toggle-btn';

            timelineToggle.onclick = () => {
                if(this.timeline.activeLayer !== layer.layerObj){
                    if (layer.layerObj.timeseries) { 
                        this.timeline.setActiveLayer(layer.layerObj);
                    }
                } else {
                    this.timeline.setActiveLayer(null);
                }
            };
            // Legend toggle button
            const legendToggle = document.createElement('button');
            legendToggle.textContent = 'Legend';
            legendToggle.className = 'legend-toggle-btn';

            // Legend container
            const legendDiv = document.createElement('div');
            legendDiv.className = 'layer-legend';
            legendDiv.style.display = layer.active ? 'block' : 'none'; // Show if active

            // Example: legend as image
            if (layer.layerObj.legend) {
                legendDiv.innerHTML = `<img src="${layer.layerObj.legend}" alt="Legend for ${layer.layerObj?.title || layerName}" style="max-width:100%;">`;
            } else {
                legendDiv.innerHTML = '<em>No legend available</em>';
            }

            legendToggle.onclick = () => {
                legendDiv.style.display = legendDiv.style.display === 'none' ? 'block' : 'none';
            };

            checkbox.onchange = (e) => this.onLayerChange(e, layer, legendDiv);

            line1.appendChild(checkbox);
            line1.appendChild(label);

            // Description line (from config.ini info field)
            const desc = document.createElement('div');
            desc.className = 'layer-description';
            desc.innerHTML = layer.layerObj.info || '';

            // Information link
            const infoLink = document.createElement('a');
            infoLink.href = "#";
            infoLink.className = 'layer-info-link';
            infoLink.textContent = "More info";
            infoLink.style.marginLeft = "28px";
            infoLink.onclick = (e) => {
                e.preventDefault();
                this.getLayerInfo(layerName);
            };

            // Add description and info link
            const descWrapper = document.createElement('div');
            descWrapper.appendChild(desc);
            descWrapper.appendChild(infoLink);

            // Legend toggle wrapper
            const legendToggleWrapper = document.createElement('div');
            legendToggleWrapper.appendChild(legendToggle);
            legendToggleWrapper.style.marginLeft = "28px";
            if(layer.layerObj.timeseries){
                legendToggleWrapper.appendChild(timelineToggle);
            }

            // Second line: slider
            const line2 = document.createElement('div');
            line2.style.display = 'flex';
            line2.style.alignItems = 'center';
            line2.style.gap = '8px';
            line2.style.marginTop = '4px';
            line2.style.marginLeft = '28px';

            const opacityLabel = document.createElement('span');
            opacityLabel.textContent = 'Opacity:   ';

            line2.appendChild(opacityLabel);

            // Second line: slider
            const line3 = document.createElement('div');
            line3.style.display = 'flex';
            line3.style.alignItems = 'center';
            line3.style.gap = '8px';
            line3.style.marginTop = '4px';
            line3.style.marginLeft = '28px';

            const opacityLabel2 = document.createElement('span');
            opacityLabel2.textContent = '0%  ';

            const slider = document.createElement('input');
            slider.type = 'range';
            slider.min = 0;
            slider.max = 1;
            slider.step = 0.01;
            slider.value = layer.opacity;
            slider.setAttribute('data-layer-opacity', layerName);
            slider.className = 'layer-slider';
            slider.style.width = '120px'; // Make slider narrower
            slider.oninput = (e) => {
                if (layer.layerObj) {
                    layer.layerObj.setOpacity(parseFloat(e.target.value));
                }
            };

            const opacityLabel3 = document.createElement('span');
            opacityLabel3.textContent = ' 100%';

            
            line3.appendChild(opacityLabel2);
            line3.appendChild(slider);
            line3.appendChild(opacityLabel3);

            wrapper.appendChild(line1);              // First line: checkbox + label
            wrapper.appendChild(line2);              // Second line: description + info link
            wrapper.appendChild(line3);              // Third line: slider
            wrapper.appendChild(descWrapper);        // Fourth line: description + info link
            if (layer.layerObj.topic !== 'facilities') {
                wrapper.appendChild(legendToggleWrapper);// Fifth line: legend toggle button
                wrapper.appendChild(legendDiv);          // Sixth line: legend
            }

            this.contentDiv.appendChild(wrapper);
        }
    }

    onLayerChange(e, layer, legendDiv) {
        if (e.target.checked) {
            if(layer.layerObj.topic !== 'facilities'){
                // Uncheck all layers in all topics in the data structure
                for (const topic in this.layersByTopic) {
                    for (const otherLayerName in this.layersByTopic[topic]) {
                        const otherLayer = this.layersByTopic[topic][otherLayerName];
                        if (otherLayer !== layer && otherLayer.layerObj.topic !== 'facilities') {
                            otherLayer.active = false;
                            if (otherLayer.layerObj && this.map.hasLayer(otherLayer.layerObj)) {
                                this.removeLayer(otherLayer.layerObj);
                            }
                        }
                    }
                }
            }
            // Set the selected layer as active
            layer.active = true;
            if (layer.layerObj) {
                layer.layerObj.addTo(this.map);
                if (layer.layerObj.topic !== 'facilities') {
                    if (layer.layerObj.timeseries) {
                        this.timeline.setActiveLayer(layer.layerObj);
                    } else {
                        this.timeline.setActiveLayer(null);
                    }
                }
            }
            legendDiv.style.display = 'block';
        } else {
            layer.active = false;
            if (layer.layerObj) {
                this.removeLayer(layer.layerObj);
                if (layer.layerObj.timeseries) {
                    this.timeline.setActiveLayer(null);
                }
            }
            legendDiv.style.display = 'none';
        }
        // Re-render controls to update checkboxes
        this.renderLayerControls();
    }

    removeLayer(layer) {
        const btn = document.getElementById('info-toggle-btn');
        if (btn && this.parent.infoActive) {
            btn.click(); // Deactivate info mode if active
        }
        this.map.removeLayer(layer);
        this.parent.activeDate = null;
    }

    getLayerInfo(layerName) {
        fetch(`/get_product_info/${layerName}`)
        .then(response => response.json())
        .then(data => {
            // Build modal content with all key-value pairs
            let modalContent = '<div>';
            for (const key in data) {
                if (typeof data[key] === 'object' && data[key] !== null) {
                    modalContent += `<strong>${key}:</strong><br>`;
                    for (const subKey in data[key]) {
                        modalContent += `&nbsp;&nbsp;${subKey}: ${data[key][subKey]}<br>`;
                    }
                } else {
                    modalContent += `<strong>${key}:</strong> ${data[key]}<br>`;
                }
            }
            // Metadata link
            const metadataLink = data?.metadata ? data.metadata : `${this.parent.localhost}/get_metadata/${layerName}`;
            modalContent += `<br><a href="${metadataLink}" target="_blank">Metadata</a></div>`;

            const modal = new ModalWidget({
                title: `Layer Info: ${layerName}`,
                content: modalContent
            });
            modal.open();
        })
        .catch(error => {
            console.error('Error fetching layer info:', error);
        });
    }
}

/**
 * Timeline widget for controlling time-based data visualization.
 */
class TimelineWidget extends Widget {
    constructor(options) {
        options.id = options.id || 'timeline-widget';
        options.title = options.title || '';
        super(options);

        this.map = options.map;
        this.parent = options.parent;
        this.allDates = options.dates || []; // Full array of date strings
        this.dates = []; // Filtered array of date strings
        this.parent.activeDate = this.allDates.length > 0 ? this.allDates[0] : null;
        this.currentIndex = 0;
        this.isPlaying = false;
        this.interval = null;

        this.activeLayer = null;
        this.dateFormat = options.dateFormat || 'yyyy-mm-dd';

        // New attributes
        this.dateInit = null;
        this.dateEnd = null;

        // Date pickers
        this.dateFromPicker = null;
        this.dateToPicker = null;


        //close button in header
        this.header.innerHTML = `<span>${this.title}</span><span class="widget-toggle">x</span>`;
        this.header.onclick = () => this.close();

        this.renderTimeline();
        this.setWidgetStyle();
    }

    close() {
        this.setActiveLayer(null);
    }

    setWidgetStyle() {
        this.container.style.position = 'absolute';
        this.container.style.left = '0';
        this.container.style.bottom = '0';
        this.container.style.width = '100%';
        this.container.style.borderRadius = '0';
        this.container.style.zIndex = '20';
        this.container.style.boxShadow = '0 -2px 8px rgba(44,62,80,0.08)';
        this.container.style.maxHeight = '12vh';
        this.container.style.overflow = 'hidden';
        this.container.id = 'timeline-widget';
    }

    renderTimeline() {
        this.setContent('');

        const controls = document.createElement('div');
        controls.className = 'timeline-controls';

        // Date pickers
        this.dateFromPicker = document.createElement('input');
        this.dateFromPicker.type = 'date';
        this.dateFromPicker.id = 'timeline-date-from';

        this.dateToPicker = document.createElement('input');
        this.dateToPicker.type = 'date';
        this.dateToPicker.id = 'timeline-date-to';

        // Set initial values if available
        if (this.dateInit) this.dateFromPicker.value = this.dateInit;
        if (this.dateEnd) this.dateToPicker.value = this.dateEnd;

        this.dateFromPicker.onchange = () => this.onDatePickerChange();
        this.dateToPicker.onchange = () => this.onDatePickerChange();

        // Play/pause button
        this.playPauseBtn = document.createElement('button');
        this.playPauseBtn.className = 'timeline-btn';
        this.playPauseBtn.innerHTML = '<span class="material-icons">&#9654;</span>';
        this.playPauseBtn.onclick = () => this.togglePlayPause();

        // Reload button
        this.reloadBtn = document.createElement('button');
        this.reloadBtn.className = 'timeline-btn';
        this.reloadBtn.innerHTML = '<span class="material-icons">&#8634;</span>';
        this.reloadBtn.onclick = () => this.reloadTimeline();

        // Slider
        this.slider = document.createElement('input');
        this.slider.type = 'range';
        this.slider.min = 0;
        this.slider.max = 0;
        this.slider.value = 0;
        this.slider.className = 'timeline-slider';
        this.slider.oninput = () => this.updateElements();

        // Date label
        this.dateLabel = document.createElement('span');
        this.dateLabel.className = 'timeline-date-label';
        this.dateLabel.textContent = '';

        // Add controls
        controls.appendChild(this.dateFromPicker);
        controls.appendChild(this.dateToPicker);
        controls.appendChild(this.playPauseBtn);
        controls.appendChild(this.reloadBtn);
        controls.appendChild(this.slider);
        controls.appendChild(this.dateLabel);

        this.contentDiv.appendChild(controls);

        // Set initial picker limits and calculate initial dates
        this.updateDatePickersLimits();
        this.calculateInitialDates();
    }

    calculateInitialDates() {
        // Set initial picker values if not set
        if (!this.dateFromPicker.value && this.dateInit) this.dateFromPicker.value = this.dateInit;
        if (!this.dateToPicker.value && this.dateEnd) this.dateToPicker.value = this.dateEnd;
        // Calculate initial dates array
        this.recalculateDates();
        this.currentIndex = 0;
        this.slider.value = this.currentIndex;
        this.slider.max = this.dates.length > 0 ? this.dates.length - 1 : 0;
        this.updateElements();
    }

    generateAllDates(minDate, maxDate, dateFormat) {
        const result = [];
        let min = minDate.split('-').map(Number);
        let max = maxDate.split('-').map(Number);

        if (dateFormat === "yyyy-mm") {
            let year = min[0];
            let month = min[1];
            let endYear = max[0];
            let endMonth = max[1];
            while (year < endYear || (year === endYear && month <= endMonth)) {
                let dateStr = `${year.toString().padStart(4, '0')}-${month.toString().padStart(2, '0')}-01`;
                if (dateStr >= minDate && dateStr <= maxDate) {
                    result.push(dateStr);
                }
                month++;
                if (month > 12) {
                    month = 1;
                    year++;
                }
            }
        } else if (dateFormat === "yyyy-mm-dd") {
            let year = min[0];
            let month = min[1];
            let endYear = max[0];
            let endMonth = max[1];
            while (year < endYear || (year === endYear && month <= endMonth)) {
                [1, 11, 21].forEach(day => {
                    let dateStr = `${year.toString().padStart(4, '0')}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
                    if (dateStr >= minDate && dateStr <= maxDate) {
                        result.push(dateStr);
                    }
                });
                month++;
                if (month > 12) {
                    month = 1;
                    year++;
                }
            }
        }
        return result;
    }

    setActiveLayer(layer) {
        this.activeLayer = layer;
        if (layer === null) {
            this.hide();
        } else {
            this.setDateFormat(layer.dateFormat);
            // Set dateInit and dateEnd from layer.timeBounds if available
            if (layer.minDate && layer.maxDate) {
                this.dateInit = layer.minDate;
                this.dateEnd = layer.maxDate;
                // Take allDates from timeBounds.all_dates
                this.allDates = this.generateAllDates(layer.minDate, layer.maxDate, layer.dateFormat);
            } else {
                // Fallback: use first and last date from allDates array
                this.dateInit = this.allDates.length > 0 ? this.allDates[0] : null;
                this.dateEnd = this.allDates.length > 0 ? this.allDates[this.allDates.length - 1] : null;
            }
            // Set pickers and recalculate dates
            this.updateDatePickersLimits();
            this.dateFromPicker.value = this.dateInit;
            this.dateToPicker.value = this.dateEnd;
            this.recalculateDates();
            this.currentIndex = 0;
            this.slider.value = this.currentIndex;
            this.slider.max = this.dates.length > 0 ? this.dates.length - 1 : 0;
            this.updateElements();
            if (this.hidden) {
                this.show();
            }
        }
    }

    setDateFormat(format) {
        this.dateFormat = format;
        this.updateDateLabel();
    }

    updateDatePickersLimits() {
        if (this.dateInit && this.dateEnd) {
            this.dateFromPicker.min = this.dateInit;
            this.dateFromPicker.max = this.dateEnd;
            this.dateToPicker.min = this.dateInit;
            this.dateToPicker.max = this.dateEnd;
        }
    }

    onDatePickerChange() {
        // Ensure dateFrom <= dateTo and both within allowed range
        let fromVal = this.dateFromPicker.value;
        let toVal = this.dateToPicker.value;

        // Clamp dateTo to be >= dateFrom
        if (toVal < fromVal) {
            toVal = fromVal;
            this.dateToPicker.value = toVal;
        }
        // Clamp dateFrom to be <= dateTo
        if (fromVal > toVal) {
            fromVal = toVal;
            this.dateFromPicker.value = fromVal;
        }

        // Update dateToPicker min to dateFrom
        this.dateToPicker.min = fromVal;

        // Recalculate dates array
        this.recalculateDates();
        // Reset slider
        this.currentIndex = 0;
        this.slider.value = this.currentIndex;
        this.slider.max = this.dates.length > 0 ? this.dates.length - 1 : 0;
        this.updateElements();
    }

    recalculateDates() {
        // Filter allDates array to be within [dateFrom, dateTo]
        if (!this.dateInit || !this.dateEnd) return;
        let fromVal = this.dateFromPicker.value;
        let toVal = this.dateToPicker.value;
        let allDates = this.allDates;
        this.dates = allDates.filter(d => d >= fromVal && d <= toVal);
        // Update slider max
        this.slider.max = this.dates.length > 0 ? this.dates.length - 1 : 0;
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
        const layer = this.activeLayer;
        if (layer && this.map.hasLayer(layer) && layer.timeseries) {
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

    show() {
        this.hidden = false;
        this.container.style.display = '';
        // Resize the map to leave space for the timeline widget
        const mapDiv = document.getElementById('map');
        if (mapDiv) {
            mapDiv.style.height = 'calc(100% - 15vh)';
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

/**
 * Modal widget for displaying content in a popup overlay.
 */
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

class DownloadWidget extends Widget {
    constructor(options) {
        options.id = options.id || 'download-widget';
        options.title = options.title || 'Download';
        super(options);

        this.map = options.map;
        this.activeLayer = null;
        this.bboxCoords = null;
        this.parent = options.parent;
        this.setWidgetStyle();
        this.renderContent();
        this.hidden = true;
        this.hide();
    }

    setWidgetStyle() {
        this.container.style.position = 'absolute';
        this.container.style.left = '0';
        this.container.style.bottom = '0';
        this.container.style.width = '100%';
        this.container.style.borderRadius = '0';
        this.container.style.zIndex = '20';
        this.container.style.boxShadow = '0 -2px 8px rgba(44,62,80,0.08)';
        this.container.style.height = '40vh'; // Fixed height for widget
        this.container.style.maxHeight = '40vh';
        this.container.style.overflowY = 'auto'; // Allow vertical scrolling
        this.container.id = 'download-widget';
    }

    renderContent() {
        this.setContent('');

        // First line: date pickers + download button
        const dateControls = document.createElement('div');
        dateControls.className = 'download-date-controls';

        // Left part: date pickers
        const datePickers = document.createElement('div');
        datePickers.className = 'download-date-pickers';

        const fromLabel = document.createElement('label');
        fromLabel.htmlFor = 'fromDate';
        fromLabel.textContent = 'From: ';

        this.fromDateInput = document.createElement('input');
        this.fromDateInput.type = 'date';
        this.fromDateInput.id = 'fromDate';
        this.fromDateInput.className = 'download-date-input';

        const toLabel = document.createElement('label');
        toLabel.htmlFor = 'toDate';
        toLabel.textContent = 'To: ';

        this.toDateInput = document.createElement('input');
        this.toDateInput.type = 'date';
        this.toDateInput.id = 'toDate';
        this.toDateInput.className = 'download-date-input';

        datePickers.appendChild(fromLabel);
        datePickers.appendChild(this.fromDateInput);
        datePickers.appendChild(toLabel);
        datePickers.appendChild(this.toDateInput);

        // Right part: download button
        this.downloadBtn = document.createElement('button');
        this.downloadBtn.id = 'download-btn';
        this.downloadBtn.className = 'download-btn';
        this.downloadBtn.innerHTML = '&#128190;';
        // Only enable if logged in
        if (!window.isLoggedIn) {
            this.downloadBtn.disabled = true;
            this.downloadBtn.title = "Login required to download data";
        } else {
            this.downloadBtn.onclick = () => this.downloadData();
        }

        

        // Second line: bounding box controls + file name input
        const bboxDiv = document.createElement('div');
        bboxDiv.className = 'bbox-controls';

        // Left part: bbox buttons and label
        const bboxLeft = document.createElement('div');
        bboxLeft.className = 'bbox-left';

        const drawBtn = document.createElement('button');
        drawBtn.className = 'download-btn';
        drawBtn.textContent = 'Draw Bounding Box';
        drawBtn.onclick = () => this.startDrawBBox();

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'download-btn';
        deleteBtn.textContent = 'Delete';
        deleteBtn.onclick = () => this.deleteBBox();

        this.bboxCoordsLabel = document.createElement('span');
        this.bboxCoordsLabel.className = 'bbox-coords-label';
        this.bboxCoordsLabel.textContent = 'No bounding box selected';

        bboxLeft.appendChild(drawBtn);
        bboxLeft.appendChild(deleteBtn);
        bboxLeft.appendChild(this.bboxCoordsLabel);

        // Right part: file name input
        const fileNameDiv = document.createElement('div');
        fileNameDiv.className = 'download-file-controls';

        const fileNameLabel = document.createElement('label');
        fileNameLabel.htmlFor = 'downloadFileName';
        fileNameLabel.textContent = 'File name: ';

        this.fileNameInput = document.createElement('input');
        this.fileNameInput.type = 'text';
        this.fileNameInput.id = 'downloadFileName';
        this.fileNameInput.className = 'download-file-input';
        this.fileNameInput.placeholder = 'output_file_name';

        fileNameDiv.appendChild(fileNameLabel);
        fileNameDiv.appendChild(this.fileNameInput);

        // Format dropdown
        const formatDiv = document.createElement('div');
        formatDiv.className = 'download-format-controls';

        const formatLabel = document.createElement('label');
        formatLabel.htmlFor = 'downloadFormat';
        formatLabel.textContent = 'Format: ';

        this.formatSelect = document.createElement('select');
        this.formatSelect.id = 'downloadFormat';
        this.formatSelect.className = 'download-format-select';

        const ncOption = document.createElement('option');
        ncOption.value = '.nc';
        ncOption.textContent = '.nc';
        this.formatSelect.appendChild(ncOption);

        const tifOption = document.createElement('option');
        tifOption.value = '.tif';
        tifOption.textContent = '.tif';
        this.formatSelect.appendChild(tifOption);

        this.formatSelect.value = '.nc'; // default

        formatDiv.appendChild(formatLabel);
        formatDiv.appendChild(this.formatSelect);

        // Add formatDiv after fileNameDiv
        fileNameDiv.appendChild(formatDiv);

        bboxDiv.appendChild(bboxLeft);
        //bboxDiv.appendChild(fileNameDiv);
        bboxDiv.appendChild(this.downloadBtn);
        dateControls.appendChild(datePickers);
        dateControls.appendChild(fileNameDiv);

        // Progress display element
        this.progressDiv = document.createElement('div');
        this.progressDiv.className = 'download-progress';
        this.progressDiv.style.marginTop = '8px';
        this.progressDiv.style.height = '20vh'; // Fixed height for progress
        this.progressDiv.style.overflowY = 'auto';
        this.progressDiv.style.fontSize = '0.95em';
        this.progressDiv.style.background = '#f8f8f8';
        this.progressDiv.style.border = '1px solid #ddd';
        this.progressDiv.style.padding = '8px';

        // Add both lines to the widget
        const controls = document.createElement('div');
        controls.className = 'download-controls';
        controls.appendChild(dateControls);
        controls.appendChild(bboxDiv);

        this.contentDiv.appendChild(controls);
        this.contentDiv.appendChild(this.progressDiv); // Add progress display
    }

    downloadData() {
        const table_name = this.activeLayerName ? this.activeLayerName : null;
        if(!table_name){
            alert('No active layer with data to download.');
            return;
        }
        const init_date = this.fromDateInput.value;
        const end_date = this.toDateInput.value;
        if (!init_date || !end_date) {
            alert('Please select both From and To dates.');
            return;
        }
        if (init_date > end_date) {
            alert('From date must be earlier than To date.');
            return;
        }
        // Default file name if not provided
        let fileName = '../fileExchange/downloads/';
        fileName += this.fileNameInput.value || `${table_name}_${init_date}_${end_date}`;
        // Get bounding box coordinates if available
        const bbox = this.bboxCoords
            ? {
                min_lat: this.bboxCoords.minLat,
                min_lon: this.bboxCoords.minLon,
                max_lat: this.bboxCoords.maxLat,
                max_lon: this.bboxCoords.maxLon
            }
            : {};

        // Clear previous progress messages
        this.progressDiv.innerHTML = '';
        // Disable download button
        this.downloadBtn.disabled = true;

        // Prepare POST request to initiate export 
        const format = this.formatSelect.value;
        fetch(`/admin/export_table/${table_name}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                init_date: init_date,
                end_date: end_date,
                bbox: bbox,
                output_filename: fileName,
                format: format
            })
        })
        .then(response => response.json())
        .then(result => {
            if (result.status === 'started' && result.process_id) {
                // Start polling for progress messages
                let pollingInterval = setInterval(() => {
                    fetch('/admin/progress_messages?process_id=' + encodeURIComponent(result.process_id))
                        .then(response => response.json())
                        .then(data => {
                            if (data.messages.length > 0) {
                                this.progressDiv.style.display = "block";
                                this.progressDiv.innerText = data.messages.join('\n');
                                this.progressDiv.scrollTop = this.progressDiv.scrollHeight;
                            } else {
                                //this.progressDiv.style.display = "none";
                                clearInterval(pollingInterval);
                                this.downloadBtn.disabled = false;
                            }
                        });
                }, 200); // Poll every 0.2 seconds
            } else {
                this.progressDiv.innerHTML = `<div>Error: ${result.message || 'Unexpected response'}</div>`;
                this.downloadBtn.disabled = false;
            }
        })
        .catch(error => {
            this.progressDiv.innerHTML = `<div>Error: ${error}</div>`;
            this.downloadBtn.disabled = false;
        });
    }

    updateDatePickers() {
        if (!this.activeLayer || !this.activeLayer.minDate || !this.activeLayer.maxDate) return;
        const minDate = this.activeLayer.minDate;
        const maxDate = this.activeLayer.maxDate;

        this.fromDateInput.min = minDate;
        this.fromDateInput.max = maxDate;
        this.toDateInput.min = minDate;
        this.toDateInput.max = maxDate;

        // Set default values
        this.fromDateInput.value = minDate;
        this.toDateInput.value = maxDate;
    }

    show() {
        this.hidden = false;
        this.container.style.display = '';
        // Find the active layer
        this.activeLayerName = Object.keys(this.parent.layers).find(layerName => 
            this.map.hasLayer(this.parent.layers[layerName]) && this.parent.layers[layerName].timeseries
        );
        this.activeLayer = this.parent.layers[this.activeLayerName];
        this.updateDatePickers();
        // Resize the map to leave space for the widget
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

    startDrawBBox() {
        // Use Leaflet's built-in rectangle drawing if available, or implement simple click/drag
        if (this._drawing) return;
        this._drawing = true;
        this.bboxLayer && this.map.removeLayer(this.bboxLayer);

        // Use Leaflet Draw if available
        if (window.L && L.Draw && L.Draw.Rectangle) {
            if (!this._drawControl) {
                this._drawControl = new L.Draw.Rectangle(this.map, { shapeOptions: { color: '#3388ff' } });
            }
            this._drawControl.enable();

            this.map.once('draw:created', (e) => {
                this.bboxLayer = e.layer;
                this.bboxLayer.addTo(this.map);
                this._drawing = false;
                this._drawControl.disable();
                this.setBBoxCoords(this.bboxLayer.getBounds());
            });
        } else {
            // Fallback: simple rectangle by two clicks
            let clickCount = 0;
            let corners = [];
            const onClick = (e) => {
                corners.push([e.latlng.lat, e.latlng.lng]);
                clickCount++;
                if (clickCount === 2) {
                    this.map.off('click', onClick);
                    const bounds = L.latLngBounds(corners[0], corners[1]);
                    this.bboxLayer = L.rectangle(bounds, { color: "#3388ff", weight: 2 });
                    this.bboxLayer.addTo(this.map);
                    this.setBBoxCoords(bounds);
                    this._drawing = false;
                }
            };
            this.map.on('click', onClick);
        }
    }

    setBBoxCoords(bounds) {
        // bounds: Leaflet LatLngBounds
        const sw = bounds.getSouthWest();
        const ne = bounds.getNorthEast();
        this.bboxCoords = {
            minLat: sw.lat,
            minLon: sw.lng,
            maxLat: ne.lat,
            maxLon: ne.lng
        };
        this.bboxCoordsLabel.textContent = 
            `BBox: [${sw.lat.toFixed(4)}, ${sw.lng.toFixed(4)}] to [${ne.lat.toFixed(4)}, ${ne.lng.toFixed(4)}]`;
    }

    deleteBBox() {
        if (this.bboxLayer) {
            this.map.removeLayer(this.bboxLayer);
            this.bboxLayer = null;
        }
        this.bboxCoords = null;
        this.bboxCoordsLabel.textContent = 'No bounding box selected';
        this._drawing = false;
    }

}