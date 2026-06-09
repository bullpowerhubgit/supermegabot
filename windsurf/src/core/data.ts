import { DataImportAction } from './types.js';
import * as XLSX from 'xlsx';
import * as fs from 'fs';
import * as path from 'path';

export class DataController {
  async execute(action: DataImportAction): Promise<any> {
    switch (action.action) {
      case 'importCSV':
        return this.importCSV(action.filePath!);
      case 'importExcel':
        return this.importExcel(action.filePath!);
      case 'exportCSV':
        return this.exportCSV(action.filePath!, action.data!, action.headers);
      case 'exportExcel':
        return this.exportExcel(action.filePath!, action.data!, action.headers);
      default:
        throw new Error(`Unknown data action: ${action.action}`);
    }
  }

  private async importCSV(filePath: string): Promise<any> {
    try {
      const workbook = XLSX.readFile(filePath);
      const sheetName = workbook.SheetNames[0];
      const worksheet = workbook.Sheets[sheetName];
      const data = XLSX.utils.sheet_to_json(worksheet);
      return { success: true, data, count: data.length };
    } catch (error: any) {
      throw new Error(`CSV import failed: ${error.message}`);
    }
  }

  private async importExcel(filePath: string): Promise<any> {
    try {
      const workbook = XLSX.readFile(filePath);
      const result: any = { sheets: {} };
      
      for (const sheetName of workbook.SheetNames) {
        const worksheet = workbook.Sheets[sheetName];
        const data = XLSX.utils.sheet_to_json(worksheet);
        result.sheets[sheetName] = { data, count: data.length };
      }
      
      return { success: true, ...result };
    } catch (error: any) {
      throw new Error(`Excel import failed: ${error.message}`);
    }
  }

  private async exportCSV(filePath: string, data: any[], headers?: string[]): Promise<any> {
    try {
      const worksheet = XLSX.utils.json_to_sheet(data, { header: headers });
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, 'Data');
      
      const dir = path.dirname(filePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      
      XLSX.writeFile(workbook, filePath);
      return { success: true, filePath, count: data.length };
    } catch (error: any) {
      throw new Error(`CSV export failed: ${error.message}`);
    }
  }

  private async exportExcel(filePath: string, data: any[], headers?: string[]): Promise<any> {
    try {
      const worksheet = XLSX.utils.json_to_sheet(data, { header: headers });
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, 'Data');
      
      const dir = path.dirname(filePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      
      XLSX.writeFile(workbook, filePath);
      return { success: true, filePath, count: data.length };
    } catch (error: any) {
      throw new Error(`Excel export failed: ${error.message}`);
    }
  }
}
