const fs = require('fs');
const path = require('path');
const vm = require('vm');

function main() {
  const sourcePath = process.argv[2];
  if (!sourcePath) {
    throw new Error('Missing source file path');
  }

  const absolutePath = path.resolve(sourcePath);
  const source = fs.readFileSync(absolutePath, 'utf8');
  const start = source.indexOf('function createLeafNode');
  const end = source.indexOf('Page({');

  if (start < 0 || end < 0 || end <= start) {
    throw new Error('Could not locate PRODUCT_GUIDE_TREE block');
  }

  const snippet = source.slice(start, end);
  const context = {
    console,
  };

  vm.createContext(context);
  vm.runInContext(`${snippet}\nthis.__PRODUCT_GUIDE_TREE__ = PRODUCT_GUIDE_TREE;`, context, {
    filename: absolutePath,
  });

  if (!context.__PRODUCT_GUIDE_TREE__) {
    throw new Error('Failed to evaluate PRODUCT_GUIDE_TREE');
  }

  process.stdout.write(JSON.stringify(context.__PRODUCT_GUIDE_TREE__));
}

try {
  main();
} catch (error) {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}
