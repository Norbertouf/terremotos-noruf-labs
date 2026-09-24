const map = L.map('map', { zoomControl: false }).setView([36.9, -4.5], 7.5);
L.control.zoom({ position: 'bottomright' }).addTo(map); 
L.tileLayer('https://{s}://{z}/{x}/{y}{r}.png', { attribution: '&copy; OpenStreetMap &copy; CARTO' }).addTo(map);

const state = { markers: [], charts: {} }; 
// Cambiamos el símbolo de dólar por la palabra "get" para evitar caracteres raros
const get = (id) => document.getElementById(id); 

const provinces = ['Almería', 'Cádiz', 'Córdoba', 'Granada', 'Huelva', 'Jaén', 'Málaga', 'Sevilla']; 
provinces.forEach((province) => get('location-filter').add(new Option(province, province))); 

const colorFor = (e) => { 
    if (e.magnitude < 1.5) return '#2ecc71'; 
    if (e.magnitude < 2.5) return '#f1c40f'; 
    if (e.magnitude < 3.5) return '#e67e22'; 
    return '#e74c3c'; 
};

const dateLabel = (v) => { 
    const d = new Date(v); 
    return Number.isNaN(d.getTime()) ? v : d.toLocaleString('es-ES', { timeZone: 'UTC', dateStyle: 'short', timeStyle: 'medium' }); 
};

function popup(e) { 
    const depth = e.depth === null ? 'No disponible en RSS IGN' : `${e.depth.toFixed(1)} km`; 
    const duration = e.duration || 'No publicada'; 
    const wave = e.wave_type || 'No publicado'; 
    return `<div class="popup"><b>${e.location}</b><dl><dt>Magnitud</dt><dd style="color:${colorFor(e)};font-weight:bold;">${e.magnitude.toFixed(1)}</dd><dt>Profundidad</dt><dd>${depth}</dd><dt>Fecha UTC</dt><dd>${dateLabel(e.date)}</dd><dt>Coordenadas</dt><dd>${e.lat.toFixed(3)}°, ${e.lon.toFixed(3)}°</dd><dt>Duración</dt><dd>${duration}</dd><dt>Tipo de onda</dt><dd>${wave}</dd></dl></div>`; 
}

function render(events) { 
    state.markers.forEach((m) => m.remove()); 
    state.markers = []; 
    
    events.forEach((e) => { 
        const m = L.circleMarker([e.lat, e.lon], { 
            radius: Math.max(5, e.magnitude * 3.5), 
            color: colorFor(e), 
            fillColor: colorFor(e), 
            fillOpacity: .72, 
            weight: 1.5 
        }).bindPopup(popup(e)).addTo(map); 
        m.on('mouseover', () => m.openPopup()); 
        state.markers.push(m); 
    }); 
    
    get('result-count').textContent = events.length; 
    get('table-count').textContent = `${events.length} resultados`; 
    
    get('events-table').innerHTML = events.slice().sort((a,b) => b.date.localeCompare(a.date)).slice(0, 12).map((e) => `<tr><td class="mono">${dateLabel(e.date)}</td><td><strong>${e.location}</strong></td><td><b class="mag" style="color:${colorFor(e)};">${e.magnitude.toFixed(1)}</b></td><td class="mono">${e.depth === null ? 'No disponible' : `\${e.depth.toFixed(1)} km`}</td><td class="mono">${e.lat.toFixed(3)}°, ${e.lon.toFixed(3)}°</td><td class="mono">${e.duration || e.wave_type || 'No publicada'}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">No hay eventos con estos filtros.</td></tr>'; 
    updateStats(events); 
    updateCharts(events); 
}

function updateStats(events) { 
    const now = new Date(); 
    const month = events.filter(e => { 
        const d = new Date(e.date); 
        return d.getUTCMonth() === now.getUTCMonth() && d.getUTCFullYear() === now.getUTCFullYear(); 
    }); 
    const max = events.reduce((a,b) => a.magnitude > b.magnitude ? a : b, { magnitude: 0 }); 
    const depths = events.filter(e => e.depth !== null); 
    get('total-month').textContent = month.length; 
    get('max-mag').textContent = max.magnitude.toFixed(1); 
    get('max-location').textContent = max.location || 'sin registros'; 
    get('avg-depth').textContent = depths.length ? `${(depths.reduce((sum,e) => sum + e.depth, 0) / depths.length).toFixed(1)}` : 'N/D'; 
    get('last-24h').textContent = events.filter(e => now - new Date(e.date) < 86400000).length; 
}

function updateCharts(events) { 
    const labels = ['0–1', '1–2', '2–3', '3–4', '4+']; 
    const values = labels.map((_, i) => events.filter(e => e.magnitude >= i && e.magnitude < (i === 4 ? 99 : i + 1)).length); 
    const depth = [events.filter(e => e.depth !== null && e.depth < 10).length, events.filter(e => e.depth !== null && e.depth >= 10 && e.depth < 30).length, events.filter(e => e.depth !== null && e.depth >= 30).length, events.filter(e => e.depth === null).length]; 
    Object.values(state.charts).forEach(c => c.destroy()); 
    
    state.charts.magnitude = new Chart(get('magnitude-chart'), { 
        type: 'bar', 
        data: { labels, datasets: [{ data: values, backgroundColor: ['#2ecc71','#f1c40f','#e67e22','#e74c3c','#111111'], borderRadius: 3, barPercentage: .62 }] }, 
        options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: '#b8b8b8' }, ticks: { precision: 0 } } }, plugins: { legend: { display: false } } } 
    }); 
    
    state.charts.depth = new Chart(get('depth-chart'), { 
        type: 'doughnut', 
        data: { labels: ['< 10 km', '10–30 km', '> 30 km', 'Sin dato'], datasets: [{ data: depth, backgroundColor: ['#e74c3c','#e5a33f','#276c69','#111111'], borderWidth: 1, borderColor: '#ffffff' }] }, 
        options: { plugins: { legend: { position: 'bottom' } }, cutout: '68%' } 
    }); 
}

async function load() { 
    const params = new URLSearchParams({ 
        min_magnitude: get('magnitude-filter').value, 
        location: get('location-filter').value, 
        date_from: get('date-from').value, 
        date_to: get('date-to').value 
    }); 
    
    try { 
        const response = await fetch(`/api/earthquakes?${params}`); 
        const data = await response.json(); 
        
        const norte = 38.8;
        const sur = 35.0;
        const este = -1.6;
        const oeste = -7.6;
        
        const eventosAndalucia = data.events.filter(e => {
            return e.lat >= sur && e.lat <= norte && e.lon >= oeste && e.lon <= este;
        });
        
        render(eventosAndalucia); 
        get('last-update').textContent = dateLabel(data.updated); 
        get('data-status').textContent = data.status === 'live' ? '● Feed IGN conectado (Filtrado Andalucía)' : '○ Mostrando última captura'; 
    } catch { 
        get('data-status').textContent = 'No se pudo conectar con el servidor'; 
        render([]); 
    } 
}

get('magnitude-filter').addEventListener('input', (e) => get('magnitude-value').textContent = Number(e.target.value).toFixed(1)); 
get('apply-filters').addEventListener('click', (e) => { 
    e.preventDefault(); 
    load(); 
}); 
get('reset-filters').addEventListener('click', () => { 
    get('location-filter').value = ''; 
    get('magnitude-filter').value = 0; 
    get('magnitude-value').textContent = '0.0'; 
    get('date-from').value = ''; 
    get('date-to').value = ''; 
    load(); 
}); 
get('theme-toggle').addEventListener('click', () => { 
    document.body.classList.toggle('dark'); 
    get('theme-toggle').textContent = document.body.classList.contains('dark') ? '☀' : '☾'; 
    load();
}); 

load();
