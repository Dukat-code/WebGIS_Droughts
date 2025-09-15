class Map{
    map;

    constructor(cfg,name){
        this.layers={};
        this.map = L.map(name,{
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

        // Add layers
        for( const layerName in cfg.layers ) {
            this.addLayer(
                layerName, 
                cfg.layers[layerName].url, 
                cfg.layers[layerName].active==='true',
                cfg.layers[layerName].opacity,
                cfg.layers[layerName].tms==='true',
                cfg.layers[layerName].time==='true'
            ) 
        }

        // Add layer control
        this.addCustomLayerControl();

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
        this.setTimeSlider(availableDates);

        // feature info on click
        this.map.on('click', (e) => {
            // Get clicked coordinates
            const latlng = e.latlng;
            // Call your info function
            this.getFeatureInfo(latlng);
        });
    }

    addLayer(layerName, layerUrl, active=true, opacity=1.0, tms=false, time=false) {
        const options = tms ? {tms: true} : {};
        this.layers[layerName] = L.tileLayer(layerUrl, options);
        this.layers[layerName].timeseries = time;
        if(active){
            this.map.addLayer(this.layers[layerName]);
            this.layers[layerName].setOpacity(opacity);
            if(time){
                document.getElementById('time-control').classList.remove('time-control-hidden');
            }
        } 
    }

    addCustomLayerControl() {
        // Create the main control container
        const wrapperDiv = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-custom-wrapper');

        // Create the icon/button
        const iconDiv = document.createElement('div');
        iconDiv.className = 'leaflet-custom-icon';
        iconDiv.innerHTML = '<span>&#9776;</span>'; // hamburger icon
        wrapperDiv.appendChild(iconDiv);

        // Create the expanded content
        const controlDiv = document.createElement('div');
        controlDiv.className = 'leaflet-custom-content';

        // close button inside the control
        const closeBtn = document.createElement('button');
        closeBtn.innerText = '✖';
        closeBtn.className = 'leaflet-custom-close-btn';
        closeBtn.onclick = () => {
            isOpen = false;
            controlDiv.style.display = 'none';
            wrapperDiv.classList.remove('leaflet-custom-wrapper-expanded');
            iconDiv.style.display = 'block';
        };
        controlDiv.appendChild(closeBtn);

        for (const layerName in this.layers) {
            // Checkbox for layer visibility
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = this.map.hasLayer(this.layers[layerName]);
            checkbox.onchange = (e) => {
                if (e.target.checked) {
                    this.map.addLayer(this.layers[layerName]);
                    if(this.layers[layerName].timeseries){
                        document.getElementById('time-control').classList.remove('time-control-hidden');
                    }
                } else {
                    this.map.removeLayer(this.layers[layerName]);
                    if(this.layers[layerName].timeseries){
                        document.getElementById('time-control').classList.add('time-control-hidden');
                    }
                }
            };

            // Label for layer name
            const label = document.createElement('label');
            label.className = 'leaflet-custom-label';
            label.innerText = ` ${layerName} `;

            // Opacity slider
            const slider = document.createElement('input');
            slider.type = 'range';
            slider.min = 0;
            slider.max = 1;
            slider.step = 0.01;
            slider.value = this.layers[layerName].options.opacity || 1;
            slider.className = 'leaflet-custom-slider';
            slider.oninput = (e) => {
                this.layers[layerName].setOpacity(e.target.value);
            };

            // Container for one layer
            const layerContainer = document.createElement('div');
            layerContainer.className = 'leaflet-custom-layer-container';
            layerContainer.appendChild(checkbox);
            layerContainer.appendChild(label);
            layerContainer.appendChild(slider);

            controlDiv.appendChild(layerContainer);
        }

        wrapperDiv.appendChild(controlDiv);

        // Click behavior to toggle open/close
        let isOpen = false;
        iconDiv.onclick = () => {
            isOpen = !isOpen;
            if (isOpen) {
                iconDiv.style.display = 'none';
                wrapperDiv.classList.add('leaflet-custom-wrapper-expanded');
                controlDiv.style.display = 'block';
            } else {
                controlDiv.style.display = 'none';
                wrapperDiv.classList.remove('leaflet-custom-wrapper-expanded');
                iconDiv.style.display = 'block';
            }
        };

        L.DomEvent.disableClickPropagation(wrapperDiv);

        const CustomLayerControl = L.Control.extend({
            options: { position: 'topright' },
            onAdd: function() {
                return wrapperDiv;
            }
        });

        this.map.addControl(new CustomLayerControl());
    }

    setTimeSlider(dates) {
        const slider = document.getElementById('time-slider');
        const label = document.getElementById('time-label');
        slider.max = dates.length - 1;
        slider.value = 0;
        label.innerText = dates[0];

        slider.oninput = (e) => {
            const date = dates[e.target.value];
            label.innerText = date;
            for (const layerName in this.layers) {
                if (this.map.hasLayer(this.layers[layerName]) && this.layers[layerName].timeseries) {
                    const baseUrl = this.layers[layerName]._url;
                    // Update the TIME parameter in the URL and refresh the layer
                    const newUrl = baseUrl.replace(/TIME=[^&]*/, `TIME=${date}`);
                    this.map.removeLayer(this.layers[layerName]);
                    this.layers[layerName].setUrl(newUrl);
                    this.map.addLayer(this.layers[layerName]);
                }
            }
        };
    }

    getFeatureInfo(latlng) {
        const lat = latlng.lat.toFixed(4);
        const lon = latlng.lng.toFixed(4);
        const date = document.getElementById('time-label').innerText;
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
                        <a href="http://localhost:5000/clim_chart/${activeLayer}/${lat}/${lon}/1991/2024" target="_blank">Open chart</a>
                    </div>
                `;

                // Open popup at the clicked location
                L.popup()
                    .setLatLng(latlng)
                    .setContent(popupContent)
                    .openOn(this.map);
            })
            .catch(error => {
                console.error('Error fetching feature info:', error);
            });
        
    }
}