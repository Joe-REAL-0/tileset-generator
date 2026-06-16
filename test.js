const jsdom = require("jsdom");
const { JSDOM } = jsdom;

const dom = new JSDOM(`
<div class="message-content">
    <div>alt text</div>
    <img src="/old.png" class="message-image large">
    <div class="surface-adjust">
        <label>容差</label>
        <input type="range" value="32">
        <button id="btn">更新</button>
    </div>
</div>
`);

const btn = dom.window.document.getElementById('btn');
const contentDiv = btn.closest('.message-content');
const imgEl = contentDiv.querySelector('img.message-image');
console.log(imgEl.src);
imgEl.src = "/new.png?t=123";
console.log(imgEl.src);
