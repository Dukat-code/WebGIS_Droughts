var chart = null;
const monthNames = [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                    ];
function createElements(lat,lon,year_init,year_end,table){
    console.log(lat);
    console.log(lon);
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
        table
    );

    getData(
        lat,
        lon,
        +yearFrom.value,
        +monthFromSlider.value+1,
        +yearTo.value,
        +monthToSlider.value+1,
        table
    );

}

function getData(lat,lon,yearFrom,monthFrom,yearTo,monthTo,table){
    console.log(yearFrom);
    console.log(monthFrom);
    console.log(yearTo);
    console.log(monthTo);
    fetch(`http://127.0.0.1:5000/get_data_from_lat_lon/${lat}/${lon}/${yearFrom}/${monthFrom}/${yearTo}/${monthTo}/${table}`)
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
    })
}


function draw_chart(data,avg,stdPlus,stdMinus,labels)
{
    const ctx = document.getElementById('myChart');
    const backgroundColors = data.map((v,i)=>v>avg[i]?'rgba(56, 140, 193, 0.8)':'rgba(62, 167, 234, 0.48)');
    if(chart) chart.destroy();
    chart = new Chart(ctx, {
        data: {
        labels: labels,
        datasets: [
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
            },
            {   
                type: 'bar',
                label: 'data',
                data: data,
                borderColor: 'rgba(0, 75, 123, 1)',
                backgroundColor: backgroundColors,
                borderWidth: 1
            }
        ]},
        options: {
        scales: {
            y: {
            beginAtZero: true
            }
        }
        }
    });
}