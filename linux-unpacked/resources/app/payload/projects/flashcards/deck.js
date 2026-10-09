let nextId = 1;
const cards = [];
export function addCard(question, answer) {
    cards.push({ id: nextId, question, answer, known: false });
    nextId += 1;
}
export function removeCard(id) {
    for (let i = 0; i < cards.length; i += 1) {
        if (cards[i].id === id) {
            cards.splice(i, 1);
            return;
        }
    }
}
export function getCards() { return cards; }
export function getTotal() { return cards.length; }
export function markKnown(id) {
    for (const c of cards) {
        if (c.id === id)
            c.known = true;
    }
}
export function getKnown() { return cards.filter(c => c.known).length; }
