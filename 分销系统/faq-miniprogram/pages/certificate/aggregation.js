function normalizeName(value) {
  return String(value || '').trim();
}

function mergeModelsAcrossCategories(categoryGroups = []) {
  const mergedMap = new Map();

  (Array.isArray(categoryGroups) ? categoryGroups : []).forEach((group) => {
    const categoryName = normalizeName(group && group.name);
    const models = Array.isArray(group && group.models) ? group.models : [];

    models.forEach((model) => {
      const modelName = normalizeName(model && model.name);
      if (!modelName) {
        return;
      }

      if (!mergedMap.has(modelName)) {
        mergedMap.set(modelName, {
          id: modelName,
          name: modelName,
          count: 0,
          categoryNames: []
        });
      }

      const current = mergedMap.get(modelName);
      current.count += Number(model && model.count) || 0;
      if (categoryName && !current.categoryNames.includes(categoryName)) {
        current.categoryNames.push(categoryName);
      }
    });
  });

  return Array.from(mergedMap.values());
}

function mergeDetailRecordGroups(detailGroups = []) {
  const seenIds = new Set();
  const merged = [];

  (Array.isArray(detailGroups) ? detailGroups : []).forEach((group) => {
    (Array.isArray(group) ? group : []).forEach((record) => {
      const id = record && record.id;
      const key = String(id);
      if (!id || seenIds.has(key)) {
        return;
      }
      seenIds.add(key);
      merged.push(record);
    });
  });

  return merged;
}

module.exports = {
  mergeModelsAcrossCategories,
  mergeDetailRecordGroups
};
