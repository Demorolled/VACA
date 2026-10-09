export function deriveNodeId(label) {
    return label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'node';
}
export function flattenSuggestedWidgets(nodes) {
    const widgets = [];
    let widgetIndex = 0;
    for (const node of nodes) {
        const nodeId = deriveNodeId(node.label);
        const suggestions = node.suggestedWidgets || [];
        for (const sw of suggestions) {
            const widgetId = sw.id || `widget_${widgetIndex}_${Date.now()}`;
            widgets.push({
                id: widgetId,
                type: sw.type,
                label: sw.label,
                x: sw.x ?? (30 + (widgetIndex * 30) % 700),
                y: sw.y ?? (60 + Math.floor(widgetIndex / 5) * 80),
                width: sw.width ?? getDefaultWidth(sw.type),
                height: sw.height ?? getDefaultHeight(sw.type),
                nodeId,
                archBindings: {
                    onClick: sw.bind?.onClick,
                    onChange: sw.bind?.onChange,
                    displayInput: sw.bind?.displayInput,
                    valueInput: sw.bind?.valueInput,
                },
                category: inferCategory(sw.type, sw.zone),
                zone: sw.zone,
            });
            widgetIndex++;
        }
    }
    return widgets;
}
function getDefaultWidth(type) {
    switch (type) {
        case 'button': return 120;
        case 'slider': return 220;
        case 'toggle': return 56;
        case 'knob': return 52;
        case 'display': return 280;
        case 'input': return 220;
        case 'label': return 120;
        default: return 120;
    }
}
function getDefaultHeight(type) {
    switch (type) {
        case 'button': return 36;
        case 'slider': return 28;
        case 'toggle': return 28;
        case 'knob': return 52;
        case 'display': return 100;
        case 'input': return 32;
        case 'label': return 24;
        default: return 36;
    }
}
function inferCategory(type, zone) {
    if (zone === 'topbar')
        return 'navigation';
    if (zone === 'bottom')
        return 'media';
    if (type === 'display')
        return 'data';
    if (type === 'slider' || type === 'knob')
        return 'media';
    return 'utility';
}
