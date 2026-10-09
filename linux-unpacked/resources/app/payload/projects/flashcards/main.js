import { addCard, removeCard, getCards, getTotal, markKnown, getKnown } from "./deck.js";
function render(ul, cnt) {
    ul.innerHTML = "";
    for (const c of getCards()) {
        const q = document.createElement("p");
        q.textContent = c.question;
        const a = document.createElement("p");
        a.textContent = c.answer;
        const kn = document.createElement("p");
        kn.textContent = c.known ? "Known" : "To learn";
        const learn = document.createElement("button");
        learn.onclick = () => { markKnown(c.id); render(ul, cnt); };
        const del = document.createElement("button");
        del.onclick = () => { removeCard(c.id); render(ul, cnt); };
        ul.appendChild(q);
        ul.appendChild(a);
        ul.appendChild(kn);
        ul.appendChild(learn);
        ul.appendChild(del);
    }
    cnt.textContent = `${getKnown()} known of ${getTotal()} cards`;
}
const inQ = document.createElement("input");
const inA = document.createElement("input");
const add = document.createElement("button");
add.textContent = "Add card";
const list = document.createElement("ul");
const counter = document.createElement("p");
add.onclick = () => {
    const q = inQ.value.trim(), a = inA.value.trim();
    if (!q)
        return;
    addCard(q, a);
    inQ.value = "";
    render(list, counter);
};
render(list, counter);
document.body.append(inQ, inA, add, counter, list);
