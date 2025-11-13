var chart = null;
let year_init, year_end, colorMin, colorMax, chart_style;
const monthNames = [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                    ];

function createElements(lat,lon,layer,year_init,year_end, color_min, color_max, style){
    console.log(lat,lon,layer,year_init,year_end, color_min, color_max, style);

    if(style && (style !== 'null')){
        console.log('Using SLD for colors');
        console.log(style)
        chart_style = style;
    } else {
        colorMin = color_min&&(color_min!=='None')?color_min:'rgba(56, 140, 193, 0.8)';
        colorMax = color_max&&(color_max!=='None')?color_max:'rgba(62, 167, 234, 0.48)';
    }
    console.log(colorMin,colorMax);
    let container = document.getElementById("container");
    let yearFromSlider = document.getElementById("yearFromSlider");
    yearFromSlider.value = year_init;
    let yearFrom = document.getElementById("yearFrom");
    yearFrom.value = yearFromSlider.value;
    yearFromSlider.oninput = (v)=>{yearFrom.value=yearFromSlider.value;};
    let monthFromSlider = document.getElementById("monthFromSlider");
    monthFromSlider.value=0;
    let monthFrom = document.getElementById("monthFrom");
    monthFrom.value = monthNames[monthFromSlider.value];
    monthFromSlider.oninput = (v)=>{monthFrom.value=monthNames[monthFromSlider.value];};

    let yearToSlider = document.getElementById("yearToSlider");
    yearToSlider.value=year_end;
    let yearTo = document.getElementById("yearTo");
    yearTo.value = yearToSlider.value;
    yearToSlider.oninput = (v)=>{yearTo.value=yearToSlider.value;};
    let monthToSlider = document.getElementById("monthToSlider");
    monthToSlider.value=11;
    let monthTo = document.getElementById("monthTo");
    monthTo.value = monthNames[monthToSlider.value];
    monthToSlider.oninput = (v)=>{monthTo.value=monthNames[monthToSlider.value];};

    document.getElementById("seeButton").onclick= () => getData(
        lat,
        lon,
        +yearFrom.value,
        +monthFromSlider.value+1,
        +yearTo.value,
        +monthToSlider.value+1,
        layer
    );

    getData(
        lat,
        lon,
        +yearFrom.value,
        +monthFromSlider.value+1,
        +yearTo.value,
        +monthToSlider.value+1,
        layer
    );

}

function getData(lat,lon,yearFrom,monthFrom,yearTo,monthTo,layer){
    console.log(yearFrom);
    console.log(monthFrom);
    console.log(yearTo);
    console.log(monthTo);
    fetch(`http://127.0.0.1:5000/get_data_from_lat_lon/${lat}/${lon}/${yearFrom}/${monthFrom}/${yearTo}/${monthTo}/${layer}`)
    .then(response => response.json())
    .then(r => {
        console.log(r);
        var data = [],std = [],avg = [], labels = [];
        for(y=0;y<=(yearTo-yearFrom);y++){
            let months = monthNames.map(v=>v+ " '" + (''+(yearFrom+y)).slice(-2))
            if(y===0) {
                data = data.concat(r.sample[y].slice(monthFrom-1));
                avg = avg.concat(r.avg.slice(monthFrom-1));
                std = std.concat(r.std.slice(monthFrom-1));
                labels = labels.concat(months.slice(monthFrom-1));
            } else if(y===yearTo-yearFrom) {
                data = data.concat(r.sample[y].slice(0,monthTo));
                avg = avg.concat(r.avg.slice(0,monthTo));
                std = std.concat(r.std.slice(0,monthTo));
                labels = labels.concat(months.slice(0,monthTo));
            } else {
                data = data.concat(r.sample[y]);
                avg = avg.concat(r.avg);
                std = std.concat(r.std);
                labels = labels.concat(months);
            }
        }
        let stdPlus = std.map((v,i)=>parseFloat(avg[i])+parseFloat(v));
        let stdMinus = std.map((v,i)=>parseFloat(avg[i])-parseFloat(v)).map(v=>v<0?0:v);
        console.log(stdPlus);
        console.log(stdMinus);
        console.log(labels);
        draw_chart(data,avg,stdPlus,stdMinus,labels);
        console.log(monthTo+1);
        console.log(monthNames.slice(1,10));
        document.getElementById("downloadCSVBtn").onclick = () => {
            downloadCSV(r);
        };
    })
}


function draw_chart(data,avg,stdPlus,stdMinus,labels)
{
    let backgroundColors = [];
    const ctx = document.getElementById('myChart');
    if(chart_style && (chart_style !== 'null')){
        console.log('Using SLD for colors');
        console.log(chart_style)
        backgroundColors = data.map(
            (v)=>chart_style.find(r=>{
                if(r.lower_boundary===null){
                    return v<=r.upper_boundary;
                } else if(r.upper_boundary===null){
                    return v>r.lower_boundary;
                } else {
                    return (v>r.lower_boundary)&&(v<=r.upper_boundary);
                }
            }).color
        );
        console.log(data);
        console.log(backgroundColors);
    } else {
        console.log("Using default colors");
        console.log(colorMax,colorMin);
        backgroundColors = data.map((v,i)=>v>=avg[i]?colorMax:colorMin);
        console.log(backgroundColors);
    }
    if(chart) chart.destroy();
    let data_sets = [];
    if(!chart_style || (chart_style === 'null')){
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
    console.log(data_sets);
    chart = new Chart(ctx, {
        data: {
        labels: labels,
        datasets: data_sets},
        options: {
        scales: {
            y: {
            beginAtZero: true
            }
        }
        }
    });
}

function downloadCSV(data) {
    let csvContent = "Year,Month,Data\n";
    for (let i = 0; i < data.years.length; i++) {
        for (let j = 0; j < data.sample[i].length; j++) {
            csvContent += `${data.years[i]},${j+1},${data.sample[i][j]}\n`;
        }
    }
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = "climate_data.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}