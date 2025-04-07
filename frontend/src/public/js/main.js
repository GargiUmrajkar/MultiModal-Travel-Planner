function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

function formatDuration(minutes) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h ${mins}m`;
}

function createJourneyCard(journey, type = 'preferred') {
    const card = document.createElement('div');
    card.className = 'bg-white shadow rounded-lg p-6 mb-6';
    
    const header = document.createElement('div');
    header.className = 'flex justify-between items-center mb-4';
    
    const title = document.createElement('h3');
    title.className = 'text-lg font-semibold text-gray-900';
    title.textContent = type === 'preferred' ? 'Preferred Journey' : 'Alternative Journey';
    
    const price = document.createElement('div');
    price.className = 'text-lg font-bold text-blue-600';
    price.textContent = formatCurrency(journey.total_cost);
    
    header.appendChild(title);
    header.appendChild(price);
    
    const details = document.createElement('div');
    details.className = 'space-y-4';
    
    // Outbound Journey
    const outboundSection = createJourneySection(journey.outbound, 'Outbound');
    details.appendChild(outboundSection);
    
    // Return Journey
    const returnSection = createJourneySection(journey.return_journey, 'Return');
    details.appendChild(returnSection);
    
    // Summary
    const summary = document.createElement('div');
    summary.className = 'mt-4 pt-4 border-t border-gray-200';
    summary.innerHTML = `
        <div class="grid grid-cols-2 gap-4">
            <div>
                <p class="text-sm text-gray-500">Total Time</p>
                <p class="font-medium">${formatDuration(journey.total_time)}</p>
            </div>
            <div>
                <p class="text-sm text-gray-500">Flight Cost</p>
                <p class="font-medium">${formatCurrency(journey.flight_cost)}</p>
            </div>
            <div>
                <p class="text-sm text-gray-500">Ground Transport Cost</p>
                <p class="font-medium">${formatCurrency(journey.ground_cost)}</p>
            </div>
        </div>
    `;
    
    details.appendChild(summary);
    
    card.appendChild(header);
    card.appendChild(details);
    
    return card;
}

function createJourneySection(segment, title) {
    const section = document.createElement('div');
    section.className = 'bg-gray-50 rounded-lg p-4';
    
    const header = document.createElement('h4');
    header.className = 'text-md font-semibold text-gray-900 mb-3';
    header.textContent = title;
    
    const content = document.createElement('div');
    content.className = 'space-y-3';
    
    // Ground Transport to Airport
    content.appendChild(createTransportCard(segment.ground_to_airport, 'To Airport'));
    
    // Flight Details
    content.appendChild(createFlightCard(segment.flight));
    
    // Ground Transport from Airport
    content.appendChild(createTransportCard(segment.ground_from_airport, 'From Airport'));
    
    section.appendChild(header);
    section.appendChild(content);
    
    return section;
}

function createTransportCard(transport, title) {
    const card = document.createElement('div');
    card.className = 'bg-white rounded p-3 shadow-sm';
    
    card.innerHTML = `
        <div class="flex justify-between items-center">
            <div>
                <p class="text-sm font-medium text-gray-900">${title}</p>
                <p class="text-sm text-gray-500">${transport.recommended_mode}</p>
            </div>
            <div class="text-right">
                <p class="text-sm font-medium text-gray-900">${formatCurrency(transport.cost_usd)}</p>
                <p class="text-sm text-gray-500">${formatDuration(transport.duration_mins)}</p>
            </div>
        </div>
        ${transport.notes ? `<p class="text-sm text-gray-500 mt-2">${transport.notes}</p>` : ''}
    `;
    
    return card;
}

function createFlightCard(flight) {
    const card = document.createElement('div');
    card.className = 'bg-white rounded p-3 shadow-sm border border-blue-100';
    
    card.innerHTML = `
        <div class="flex justify-between items-center">
            <div>
                <p class="text-sm font-medium text-gray-900">${flight.airline}</p>
                <p class="text-sm text-gray-500">${flight.origin} → ${flight.destination}</p>
            </div>
            <div class="text-right">
                <p class="text-sm font-medium text-gray-900">${flight.price}</p>
                <p class="text-sm text-gray-500">${formatDuration(flight.flight_duration_mins)}</p>
            </div>
        </div>
        <div class="mt-2 text-sm text-gray-500">
            <p>Departure: ${flight.departure}</p>
            <p>Arrival: ${flight.arrival}</p>
            <p>Stops: ${flight.stops}</p>
        </div>
    `;
    
    return card;
}

function displayResults(data) {
    const resultsContent = document.getElementById('resultsContent');
    resultsContent.innerHTML = '';
    
    // Display preferred journey
    if (data.preferred_journey) {
        resultsContent.appendChild(createJourneyCard(data.preferred_journey, 'preferred'));
    }
    
    // Display alternative journey if available
    if (data.alternative_journey) {
        resultsContent.appendChild(createJourneyCard(data.alternative_journey, 'alternative'));
    }
    
    // Display bus options if available
    if (data.available_bus_options) {
        const busSection = document.createElement('div');
        busSection.className = 'mt-6';
        busSection.innerHTML = `
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Additional Bus Options</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                ${Object.entries(data.available_bus_options).map(([direction, options]) => `
                    <div class="bg-white shadow rounded-lg p-4">
                        <h4 class="font-medium text-gray-900 mb-2">${direction}</h4>
                        <div class="space-y-2">
                            ${options.map(option => `
                                <div class="text-sm">
                                    <p class="font-medium">${option.provider}</p>
                                    <p class="text-gray-500">${option.departure} → ${option.arrival}</p>
                                    <p class="text-gray-500">${formatCurrency(option.price)}</p>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
        resultsContent.appendChild(busSection);
    }
} 