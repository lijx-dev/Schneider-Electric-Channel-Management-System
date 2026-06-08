const assert = require('node:assert/strict');

function loadChatPage() {
  delete require.cache[require.resolve('./zhinengwenda_AI_Assistant_Green')];

  const previousGetApp = global.getApp;
  const previousRequirePlugin = global.requirePlugin;
  const previousPage = global.Page;
  let pageConfig = null;

  global.getApp = () => ({});
  global.requirePlugin = () => ({});
  global.Page = (config) => {
    pageConfig = config;
  };

  require('./zhinengwenda_AI_Assistant_Green');

  global.getApp = previousGetApp;
  global.requirePlugin = previousRequirePlugin;
  global.Page = previousPage;

  return pageConfig;
}

const page = loadChatPage();

const markdownInList = page.parseRichContent(
  '4. **Image**: ![Busbar drawing](https://example.com/busbar.jpg?sign=abc&t=1779084545)'
);

assert.equal(markdownInList.some((node) => node.type === 'image'), true);
assert.equal(
  markdownInList.find((node) => node.type === 'image').url,
  'https://example.com/busbar.jpg?sign=abc&t=1779084545'
);

const bareUrlInList = page.parseRichContent(
  '3. Image: https://example.com/layout.png?sign=xyz&t=1779084621'
);

assert.equal(bareUrlInList.some((node) => node.type === 'image'), true);
assert.equal(
  bareUrlInList.find((node) => node.type === 'image').url,
  'https://example.com/layout.png?sign=xyz&t=1779084621'
);

const markdownPdf = page.parseRichContent(
  '可以下载这个资料：[I-Line B母线样本](https://example.com/files/iline-b.pdf?sign=abc&t=1779176593)'
);

assert.equal(markdownPdf.some((node) => node.type === 'file'), true);
assert.equal(markdownPdf.find((node) => node.type === 'file').title, 'I-Line B母线样本');
assert.equal(
  markdownPdf.find((node) => node.type === 'file').url,
  'https://example.com/files/iline-b.pdf?sign=abc&t=1779176593'
);
assert.equal(markdownPdf.find((node) => node.type === 'file').fileType, 'pdf');

const barePdf = page.parseRichContent(
  'PDF: https://example.com/files/sample.PDF?sign=xyz&t=1779176593'
);

assert.equal(barePdf.some((node) => node.type === 'file'), true);
assert.equal(
  barePdf.find((node) => node.type === 'file').url,
  'https://example.com/files/sample.PDF?sign=xyz&t=1779176593'
);
assert.equal(barePdf.find((node) => node.type === 'file').fileType, 'pdf');
