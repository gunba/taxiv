import type { TaxDataObject } from '../types';
import jsonData from './ITAA1997_database.json';

export const taxDatabase: Record<string, TaxDataObject> = jsonData;
