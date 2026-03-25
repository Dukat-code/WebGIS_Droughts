var chart = null;
let colorMin, colorMax, chart_style;
const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
];

function createElements(lat, lon, layer, min_date, max_date, color_min, color_max, style, date_format) {
    // Parse min/max year from min_date/max_date
    let minYear = min_date ? parseInt(min_date.substring(0, 4)) : 1991;
    let maxYear = max_date ? parseInt(max_date.substring(0, 4)) : 2020;

    if (style && (style !== 'null')) {
        chart_style = JSON.parse(style);
    } else {
        colorMin = color_min && (color_min !== 'None') ? color_min : 'rgba(56, 140, 193, 0.8)';
        colorMax = color_max && (color_max !== 'None') ? color_max : 'rgba(62, 167, 234, 0.48)';
    }

    // Year sliders
    let yearFromSlider = document.getElementById("yearFromSlider");
    yearFromSlider.min = minYear;
    yearFromSlider.max = maxYear;
    yearFromSlider.value = minYear;
    let yearFrom = document.getElementById("yearFrom");
    yearFrom.value = yearFromSlider.value;
    yearFromSlider.oninput = () => { yearFrom.value = yearFromSlider.value; };

    let yearToSlider = document.getElementById("yearToSlider");
    yearToSlider.min = minYear;
    yearToSlider.max = maxYear;
    yearToSlider.value = maxYear;
    let yearTo = document.getElementById("yearTo");
    yearTo.value = yearToSlider.value;
    yearToSlider.oninput = () => { yearTo.value = yearToSlider.value; };

    // Month sliders
    let monthFromSlider = document.getElementById("monthFromSlider");
    monthFromSlider.value = 0;
    let monthFrom = document.getElementById("monthFrom");
    monthFrom.value = monthNames[monthFromSlider.value];
    monthFromSlider.oninput = () => { monthFrom.value = monthNames[monthFromSlider.value]; };

    let monthToSlider = document.getElementById("monthToSlider");
    monthToSlider.value = 11;
    let monthTo = document.getElementById("monthTo");
    monthTo.value = monthNames[monthToSlider.value];
    monthToSlider.oninput = () => { monthTo.value = monthNames[monthToSlider.value]; };

    // Dekad sliders (only if date_format is daily/dekad)
    let dekadFromSlider = null, dekadFromLabel = null, dekadToSlider = null, dekadToLabel = null;
    if (date_format === "yyyy-mm-dd" || date_format === "YYYY-MM-DD") {
        document.getElementById("dekadFromControl").style.display = "block";
        document.getElementById("dekadToControl").style.display = "block";

        dekadFromSlider = document.getElementById("dekadFromSlider");
        dekadFromLabel = document.getElementById("dekadFromLabel");
        dekadToSlider = document.getElementById("dekadToSlider");
        dekadToLabel = document.getElementById("dekadToLabel");

        const dekadNames = ["Dekad: 1 (Days 1-10)", "Dekad: 2 (Days 11-20)", "Dekad: 3 (Days 21-end)"];
        dekadFromSlider.oninput = function () {
            dekadFromLabel.value = dekadNames[dekadFromSlider.value];
        };
        dekadToSlider.oninput = function () {
            dekadToLabel.value = dekadNames[dekadToSlider.value];
        };
    }

    document.getElementById("seeButton").onclick = () => {
        let dekadFrom = dekadFromSlider ? (+dekadFromSlider.value + 1) : null;
        let dekadTo = dekadToSlider ? (+dekadToSlider.value + 1) : null;
        getData(
            lat,
            lon,
            +yearFrom.value,
            +monthFromSlider.value + 1,
            dekadFrom,
            +yearTo.value,
            +monthToSlider.value + 1,
            dekadTo,
            layer,
            date_format
        );
    };

    // Initial data fetch
    let dekadFrom = dekadFromSlider ? (+dekadFromSlider.value + 1) : null;
    let dekadTo = dekadToSlider ? (+dekadToSlider.value + 1) : null;
    getData(
        lat,
        lon,
        +yearFrom.value,
        +monthFromSlider.value + 1,
        dekadFrom,
        +yearTo.value,
        +monthToSlider.value + 1,
        dekadTo,
        layer,
        date_format
    );
}

function getData(lat, lon, yearFrom, monthFrom, dekadFrom, yearTo, monthTo, dekadTo, layer, date_format) {
    let url;
    if (date_format === "YYYY-MM-DD" || date_format === "yyyy-mm-dd") {
        let dateFrom = `${yearFrom}-${String(monthFrom).padStart(2, '0')}-${dekadFrom === 1 ? '01' : dekadFrom === 2 ? '11' : '21'}`;
        let dateTo = `${yearTo}-${String(monthTo).padStart(2, '0')}-${dekadTo === 1 ? '01' : dekadTo === 2 ? '11' : '21'}`;
        url = `${localhost}/get_data_from_latlon_dekad/${lat}/${lon}/${dateFrom}/${dateTo}/${layer}`;
    } else {
        url = `${localhost}/get_data_from_lat_lon/${lat}/${lon}/${yearFrom}/${monthFrom}/${yearTo}/${monthTo}/${layer}`;
    }

    fetch(url)
        .then(response => response.json())
        .then(r => {
            var data = [], std = [], avg = [], labels = [];
            if (date_format === "YYYY-MM-DD" || date_format === "yyyy-mm-dd") {
                for (let y = 0; y < r.years.length; y++) {
                    for (let m = 0; m < r.months.length; m++) {
                        for (let d = 0; d < r.dekads.length; d++) {
                            data.push(r.sample[y][m][d]);
                            avg.push(r.avg_per_dekad[d]);
                            std.push(r.std_per_dekad[d]);
                            labels.push(`${monthNames[m]} '${String(r.years[y]).slice(-2)} Dekad ${d + 1}`);
                        }
                    }
                }
            } else {
                for (let y = 0; y <= (yearTo - yearFrom); y++) {
                    let months = monthNames.map(v => v + " '" + ('' + (yearFrom + y)).slice(-2));
                    if (y === 0) {
                        data = data.concat(r.sample[y].slice(monthFrom - 1));
                        avg = avg.concat(r.avg.slice(monthFrom - 1));
                        std = std.concat(r.std.slice(monthFrom - 1));
                        labels = labels.concat(months.slice(monthFrom - 1));
                    } else if (y === yearTo - yearFrom) {
                        data = data.concat(r.sample[y].slice(0, monthTo));
                        avg = avg.concat(r.avg.slice(0, monthTo));
                        std = std.concat(r.std.slice(0, monthTo));
                        labels = labels.concat(months.slice(0, monthTo));
                    } else {
                        data = data.concat(r.sample[y]);
                        avg = avg.concat(r.avg);
                        std = std.concat(r.std);
                        labels = labels.concat(months);
                    }
                }
            }
            let stdPlus = std.map((v, i) => parseFloat(avg[i]) + parseFloat(v));
            let stdMinus = std.map((v, i) => parseFloat(avg[i]) - parseFloat(v)).map(v => v < 0 ? 0 : v);
            draw_chart(data, avg, stdPlus, stdMinus, labels);

            const fileName = layer+"_"+yearFrom+"-"+monthFrom+(dekadFrom ? ("-D"+dekadFrom) : "")+"_to_"+yearTo+"-"+monthTo+(dekadTo ? ("-D"+dekadTo) : "")+".csv";
            document.getElementById("downloadCSVBtn").onclick = () => {
                downloadCSV(r, date_format, fileName);
            };
        });
}

function draw_chart(data, avg, stdPlus, stdMinus, labels) {
    let backgroundColors = [];
    const ctx = document.getElementById('myChart');
    if (chart_style && (chart_style !== 'null')) {
        backgroundColors = data.map(
            (v) => chart_style.find(r => {
                if (r.lower_boundary === null) {
                    return v <= r.upper_boundary;
                } else if (r.upper_boundary === null) {
                    return v > r.lower_boundary;
                } else {
                    return (v > r.lower_boundary) && (v <= r.upper_boundary);
                }
            }).color
        );
    } else {
        backgroundColors = data.map((v, i) => v >= avg[i] ? colorMax : colorMin);
    }
    if (chart) chart.destroy();
    let data_sets = [];
    if (!chart_style || (chart_style === 'null')) {
        data_sets.push(
            {
                type: 'line',
                label: 'std+',
                data: stdPlus,
                borderWidth: 1,
                borderColor: 'rgba(122, 141, 171, 0.2)',
            },
            {
                type: 'line',
                label: 'std-',
                data: stdMinus,
                borderWidth: 1,
                borderColor: 'rgba(122, 141, 171, 0.2)',
                backgroundColor: 'rgba(122, 141, 171, 0.2)',
                fill: '-1'
            },
            {
                type: 'line',
                label: 'avg',
                data: avg,
                borderColor: 'rgba(230, 94, 40, 1)',
                borderWidth: 3
            }
        );
    }
    data_sets.push(
        {
            type: 'bar',
            label: 'data',
            data: data,
            borderColor: 'rgba(0, 75, 123, 1)',
            backgroundColor: backgroundColors,
            borderWidth: 1
        }
    );
    chart = new Chart(ctx, {
        data: {
            labels: labels,
            datasets: data_sets
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

function downloadCSV(data, date_format, fileName) {
    let csvContent = "";
    if (date_format === "YYYY-MM-DD" || date_format === "yyyy-mm-dd") {
        csvContent = "Year,Month,Dekad,Data\n";
        for (let i = 0; i < data.years.length; i++) {
            for (let j = 0; j < data.months.length; j++) {
                for (let k = 0; k < data.dekads.length; k++) {
                    csvContent += `${data.years[i]},${data.months[j]},${data.dekads[k]},${data.sample[i][j][k]}\n`;
                }
            }
        }
    } else {
        csvContent = "Year,Month,Data\n";
        for (let i = 0; i < data.years.length; i++) {
            for (let j = 0; j < data.sample[i].length; j++) {
                csvContent += `${data.years[i]},${j + 1},${data.sample[i][j]}\n`;
            }
        }
    }
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = fileName ? fileName : "climate_data.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}