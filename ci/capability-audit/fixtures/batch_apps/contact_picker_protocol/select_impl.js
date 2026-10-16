function checkSelectParameter(config) {
  const params = config.parameters;
  if (params.selectLimit !== undefined && (!Number.isInteger(params.selectLimit) || params.selectLimit <= 0)) {
    return false;
  }
  for (const key of ['isContactMultiSelect', 'isDisplayByName', 'isAutoDismissOnNavigation']) {
    if (params[key] !== undefined && typeof params[key] !== 'boolean') { return false; }
  }
  if (params.filter !== undefined && (params.filter === null || typeof params.filter !== 'object' ||
      Array.isArray(params.filter))) { return false; }
  if (params.selectLimit > 10000) { params.selectLimit = 10000; }
  return true;
}

function selectionError(error) {
  const code = error && typeof error.code === 'number' ? error.code : error;
  if ([201, 202, 401, 801, ERROR_SYSTEM, ERROR_QUERY_VALUE_FAILED, ERROR_INVALID_PARAMETER,
    ERROR_OVER_LIMIT].includes(code)) { return new BusinessError(code); }
  return new BusinessError(ERROR_SYSTEM);
}

function parseContacts(result) {
  if (!result || typeof result.pickerData !== 'string' || !Number.isInteger(result.total) ||
      result.total < 0 || result.total > 10000) { throw new BusinessError(ERROR_SYSTEM); }
  let contacts;
  try { contacts = JSON.parse(result.pickerData); }
  catch (_) { throw new BusinessError(ERROR_SYSTEM); }
  if (!Array.isArray(contacts) || contacts.length !== result.total ||
      contacts.some(item => item === null || typeof item !== 'object' || Array.isArray(item))) {
    throw new BusinessError(ERROR_SYSTEM);
  }
  if (result.resultCode === 1 && contacts.length !== 0) { throw new BusinessError(ERROR_SYSTEM); }
  return contacts;
}

function contactsPickerSelect(...args) {
  let callback;
  if (args.length > 2 || (args.length === 2 && typeof args[1] !== 'function') ||
      (args.length > 0 && typeof args[0] !== 'function' &&
        (args[0] === null || typeof args[0] !== 'object' || Array.isArray(args[0])))) {
    throw new BusinessError(ERROR_CODE_INVALID_PARAM, ERROR_MSG_SELECT_INVALID_PARAM);
  }
  if (args.length === 2 && typeof args[0] === 'function') {
    throw new BusinessError(ERROR_CODE_INVALID_PARAM, ERROR_MSG_SELECT_INVALID_PARAM);
  }
  if (typeof args[args.length - 1] === 'function') { callback = args[args.length - 1]; }
  const config = parseContactsPickerSelectOption(args);
  if (!checkSelectParameter(config)) {
    throw new BusinessError(ERROR_CODE_INVALID_PARAM, ERROR_MSG_SELECT_INVALID_PARAM);
  }
  const operation = (async () => {
    try {
      const context = getContext(this);
      const result = await startContactsPicker(context, config, 'select');
      if (!result || (result.resultCode !== 0 && result.resultCode !== 1)) {
        throw selectionError(result ? result.resultCode : ERROR_SYSTEM);
      }
      return parseContacts(result);
    } catch (error) { throw selectionError(error); }
  })();
  if (callback !== undefined) {
    // Only this pair settles the public callback; an exception thrown by the
    // caller's callback must never cause a second callback invocation.
    operation.then(contacts => callback(undefined, contacts), error => callback(error, undefined));
    return undefined;
  }
  return operation;
}
