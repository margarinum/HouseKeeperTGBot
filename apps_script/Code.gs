const SHEET_NAME = 'Лист1';

// Укажите свой секрет здесь и тот же в .env как GAS_SHARED_SECRET (в git не коммитить реальное значение)
const SECRET = 'change_me';
const MAX_USERS_PER_APARTMENT = 3;

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents || '{}');

    if (data.secret !== SECRET) {
      return jsonResponse({ status: 'error', message: 'Unauthorized' });
    }

    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
    if (!sheet) {
      return jsonResponse({ status: 'error', message: 'Sheet not found: ' + SHEET_NAME });
    }

    const action = data.action;

    if (action === 'ping') return jsonResponse({ status: 'ok', message: 'pong' });
    if (action === 'check_house') return checkHouse(sheet, data.house);
    if (action === 'check_entrance') return checkEntrance(sheet, data.house, data.entrance);
    if (action === 'check_floor') return checkFloor(sheet, data.house, data.entrance, data.floor);
    if (action === 'check_apartment') return checkApartment(sheet, data.house, data.entrance, data.floor, data.apartment);
    if (action === 'verify') return verifyUser(sheet, data);
    if (action === 'find_user') return findUser(sheet, data.user_id);
    if (action === 'list_users') return listUsers(sheet);
    if (action === 'remove') return removeUser(sheet, data.user_id);
    if (action === 'get_houses') return getHouses(sheet);
    if (action === 'get_all_rows') return getAllRows(sheet);
    if (action === 'set_apartment_limit') return setApartmentLimit(sheet, data.house, data.apartment, data.max_users);

    return jsonResponse({ status: 'error', message: 'Unknown action: ' + action });
  } catch (err) {
    return jsonResponse({ status: 'error', message: String(err) });
  }
}

function getData(sheet) {
  const values = sheet.getDataRange().getValues();
  const headers = values[0];

  const indexes = {
    house: headers.indexOf('Номер дома'),
    entrance: headers.indexOf('Номер подъезда'),
    floor: headers.indexOf('Этаж'),
    apartment: headers.indexOf('Номер квартиры')
  };

  if (indexes.house === -1 || indexes.entrance === -1 || indexes.floor === -1 || indexes.apartment === -1) {
    throw new Error('Required columns not found. Need: Номер дома, Номер подъезда, Этаж, Номер квартиры');
  }

  return { values, headers, indexes };
}

function normalizeValue(value) {
  return String(value || '').trim();
}

function isValidHouseInput(value) {
  const text = normalizeValue(value);
  if (!text) return false;
  if (!/^[а-яё0-9\s.\-]+$/.test(text)) return false;
  if (text !== text.toLowerCase()) return false;
  return true;
}

function findMatchingRows(sheet, filters) {
  const { values, indexes } = getData(sheet);
  const result = [];

  for (let i = 1; i < values.length; i++) {
    const row = values[i];

    if (filters.house !== undefined && normalizeValue(row[indexes.house]) !== normalizeValue(filters.house)) continue;
    if (filters.entrance !== undefined && normalizeValue(row[indexes.entrance]) !== normalizeValue(filters.entrance)) continue;
    if (filters.floor !== undefined && normalizeValue(row[indexes.floor]) !== normalizeValue(filters.floor)) continue;
    if (filters.apartment !== undefined && normalizeValue(row[indexes.apartment]) !== normalizeValue(filters.apartment)) continue;

    result.push({ rowIndex: i + 1, row: row });
  }

  return result;
}

function checkHouse(sheet, house) {
  if (!isValidHouseInput(house)) {
    return jsonResponse({ status: 'ok', exists: false, message: 'Номер дома должен быть кириллицей в нижнем регистре' });
  }
  return jsonResponse({ status: 'ok', exists: findMatchingRows(sheet, { house }).length > 0 });
}

function checkEntrance(sheet, house, entrance) {
  if (!isValidHouseInput(house)) return jsonResponse({ status: 'ok', exists: false });
  return jsonResponse({ status: 'ok', exists: findMatchingRows(sheet, { house, entrance }).length > 0 });
}

function checkFloor(sheet, house, entrance, floor) {
  if (!isValidHouseInput(house)) return jsonResponse({ status: 'ok', exists: false });
  return jsonResponse({ status: 'ok', exists: findMatchingRows(sheet, { house, entrance, floor }).length > 0 });
}

function checkApartment(sheet, house, entrance, floor, apartment) {
  if (!isValidHouseInput(house)) return jsonResponse({ status: 'ok', exists: false });
  return jsonResponse({ status: 'ok', exists: findMatchingRows(sheet, { house, entrance, floor, apartment }).length > 0 });
}

function verifyUser(sheet, data) {
  const house = data.house;
  const entrance = data.entrance;
  const floor = data.floor;
  const apartment = data.apartment;
  const userId = String(data.user_id || '').trim();
  const displayName = String(data.display_name || '').trim();

  if (!userId) return jsonResponse({ status: 'error', message: 'user_id is required' });
  if (!displayName) return jsonResponse({ status: 'error', message: 'display_name is required' });
  if (!isValidHouseInput(house)) return jsonResponse({ status: 'error', message: 'Номер дома должен быть кириллицей в нижнем регистре' });

  const { headers } = getData(sheet);
  const rows = findMatchingRows(sheet, { house, entrance, floor, apartment });

  if (rows.length === 0) {
    return jsonResponse({ status: 'error', message: 'Квартира не найдена' });
  }

  removeUserInternal(sheet, userId);

  SpreadsheetApp.flush();

  const rowIndex = rows[0].rowIndex;
  const row = sheet.getRange(rowIndex, 1, 1, headers.length).getValues()[0];

  let occupiedCount = 0;
  for (let col = 0; col < headers.length; col++) {
    const header = String(headers[col] || '').trim();
    if (!/^ID\d+$/.test(header)) continue;
    const idValue = normalizeValue(row[col]);
    if (idValue) occupiedCount += 1;
  }

  const apartmentLimit = getApartmentLimit(house, apartment);
  if (occupiedCount >= apartmentLimit) {
    return jsonResponse({
      status: 'error',
      message: 'Превышено количество зарегистрированных пользователей на квартиру'
    });
  }

  for (let col = 0; col < headers.length; col++) {
    const header = String(headers[col] || '').trim();
    if (!/^Имя\d+$/.test(header)) continue;

    const number = header.replace('Имя', '');
    const idHeader = 'ID' + number;
    const idCol = headers.indexOf(idHeader);
    if (idCol === -1) continue;

    const nameValue = normalizeValue(row[col]);
    const idValue = normalizeValue(row[idCol]);

    if (!nameValue && !idValue) {
      sheet.getRange(rowIndex, col + 1).setValue(displayName);
      sheet.getRange(rowIndex, idCol + 1).setValue(userId);
      return jsonResponse({ status: 'ok', message: 'User verified' });
    }
  }

  return jsonResponse({ status: 'error', message: 'Нет свободных полей Имя/ID для этой квартиры' });
}


function listUsers(sheet) {
  const { values, headers, indexes } = getData(sheet);
  const users = [];

  for (let i = 1; i < values.length; i++) {
    const row = values[i];

    for (let col = 0; col < headers.length; col++) {
      const header = String(headers[col] || '').trim();
      if (!/^ID\d+$/.test(header)) continue;

      const userId = normalizeValue(row[col]);
      if (!userId) continue;

      const number = header.replace('ID', '');
      const nameHeader = 'Имя' + number;
      const nameCol = headers.indexOf(nameHeader);

      users.push({
        user_id: userId,
        display_name: nameCol !== -1 ? normalizeValue(row[nameCol]) : '',
        house: normalizeValue(row[indexes.house]),
        entrance: normalizeValue(row[indexes.entrance]),
        floor: normalizeValue(row[indexes.floor]),
        apartment: normalizeValue(row[indexes.apartment]),
        row_index: i + 1
      });
    }
  }

  return jsonResponse({ status: 'ok', users: users });
}

function findUser(sheet, userId) {
  const user = findUserInternal(sheet, String(userId || '').trim());
  return jsonResponse({ status: 'ok', user: user });
}

function findUserInternal(sheet, userId) {
  if (!userId) return null;

  const { values, headers, indexes } = getData(sheet);

  for (let i = 1; i < values.length; i++) {
    const row = values[i];

    for (let col = 0; col < headers.length; col++) {
      const header = String(headers[col] || '').trim();
      if (!/^ID\d+$/.test(header)) continue;

      if (normalizeValue(row[col]) === userId) {
        const number = header.replace('ID', '');
        const nameHeader = 'Имя' + number;
        const nameCol = headers.indexOf(nameHeader);

        return {
          user_id: userId,
          display_name: nameCol !== -1 ? normalizeValue(row[nameCol]) : '',
          house: normalizeValue(row[indexes.house]),
          entrance: normalizeValue(row[indexes.entrance]),
          floor: normalizeValue(row[indexes.floor]),
          apartment: normalizeValue(row[indexes.apartment]),
          row_index: i + 1
        };
      }
    }
  }

  return null;
}

function removeUser(sheet, userId) {
  const removed = removeUserInternal(sheet, String(userId || '').trim());
  return jsonResponse({ status: 'ok', removed: removed });
}

function removeUserInternal(sheet, userId) {
  if (!userId) return false;

  const { values, headers } = getData(sheet);
  let removed = false;

  for (let i = 1; i < values.length; i++) {
    const row = values[i];

    for (let col = 0; col < headers.length; col++) {
      const header = String(headers[col] || '').trim();

      if (!/^ID\d+$/.test(header)) continue;

      const currentId = normalizeValue(row[col]);

      if (currentId === userId) {
        const number = header.replace('ID', '');
        const nameHeader = 'Имя' + number;
        const nameCol = headers.indexOf(nameHeader);

        sheet.getRange(i + 1, col + 1).clearContent();

        if (nameCol !== -1) {
          sheet.getRange(i + 1, nameCol + 1).clearContent();
        }

        removed = true;
      }
    }
  }

  SpreadsheetApp.flush();

  return removed;
}

function setApartmentLimit(sheet, house, apartment, maxUsers) {
  if (!house || !apartment) {
    return jsonResponse({ status: 'error', message: 'house and apartment are required' });
  }
  maxUsers = parseInt(maxUsers, 10);
  if (isNaN(maxUsers) || maxUsers < 1) {
    return jsonResponse({ status: 'error', message: 'max_users must be a positive integer' });
  }

  const rows = findMatchingRows(sheet, { house, apartment });
  if (rows.length === 0) {
    return jsonResponse({ status: 'error', message: 'Квартира не найдена в таблице' });
  }

  // Store limit in script properties (persistent key-value store)
  const key = 'limit_' + String(house).trim() + '_' + String(apartment).trim();
  PropertiesService.getScriptProperties().setProperty(key, String(maxUsers));

  return jsonResponse({ status: 'ok', house: house, apartment: apartment, max_users: maxUsers });
}

function getApartmentLimit(house, apartment) {
  const key = 'limit_' + String(house).trim() + '_' + String(apartment).trim();
  const val = PropertiesService.getScriptProperties().getProperty(key);
  return val !== null ? parseInt(val, 10) : MAX_USERS_PER_APARTMENT;
}

function getAllRows(sheet) {
  const { values, indexes } = getData(sheet);
  const rows = [];
  for (let i = 1; i < values.length; i++) {
    const row = values[i];
    const house    = String(row[indexes.house]    || '').trim();
    const entrance = String(row[indexes.entrance] || '').trim();
    const floor    = String(row[indexes.floor]    || '').trim();
    const apartment= String(row[indexes.apartment]|| '').trim();
    if (house) rows.push({ house, entrance, floor, apartment });
  }
  return jsonResponse({ status: 'ok', rows: rows });
}

function getHouses(sheet) {
  const { values, indexes } = getData(sheet);
  const housesSet = {};

  for (let i = 1; i < values.length; i++) {
    const house = String(values[i][indexes.house] || '').trim();
    if (house) housesSet[house] = true;
  }

  const houses = Object.keys(housesSet).sort();
  return jsonResponse({ status: 'ok', houses: houses });
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
