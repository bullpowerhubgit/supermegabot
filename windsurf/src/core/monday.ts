import { MondayConfig, MondayAction } from './types.js';
import axios from 'axios';

export class MondayController {
  private config: MondayConfig;
  private baseUrl = 'https://api.monday.com/v2';

  constructor(config: MondayConfig) {
    this.config = config;
  }

  async execute(action: MondayAction): Promise<any> {
    switch (action.action) {
      case 'getBoards':
        return this.getBoards();
      case 'getBoard':
        return this.getBoard(action.boardId!);
      case 'getItems':
        return this.getItems(action.boardId!);
      case 'getItem':
        return this.getItem(action.itemId!);
      case 'createItem':
        return this.createItem(action.boardId!, action.data);
      case 'updateItem':
        return this.updateItem(action.itemId!, action.data);
      case 'deleteItem':
        return this.deleteItem(action.itemId!);
      case 'getColumns':
        return this.getColumns(action.boardId!);
      default:
        throw new Error(`Unknown Monday action: ${action.action}`);
    }
  }

  private async getBoards(): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: '{ boards { id name } }' }, {
        headers: { Authorization: this.config.apiKey },
      });
      return { success: true, boards: response.data.data.boards };
    } catch (error: any) {
      throw new Error(`Monday getBoards failed: ${error.message}`);
    }
  }

  private async getBoard(boardId: string): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: `{ boards (ids: [${boardId}]) { id name } }` }, {
        headers: { Authorization: this.config.apiKey },
      });
      return { success: true, board: response.data.data.boards[0] };
    } catch (error: any) {
      throw new Error(`Monday getBoard failed: ${error.message}`);
    }
  }

  private async getItems(boardId: string): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: `{ boards (ids: [${boardId}]) { items { id name } } }` }, {
        headers: { Authorization: this.config.apiKey },
      });
      return { success: true, items: response.data.data.boards[0].items };
    } catch (error: any) {
      throw new Error(`Monday getItems failed: ${error.message}`);
    }
  }

  private async getItem(itemId: string): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: `{ items (ids: [${itemId}]) { id name } }` }, {
        headers: { Authorization: this.config.apiKey },
      });
      return { success: true, item: response.data.data.items[0] };
    } catch (error: any) {
      throw new Error(`Monday getItem failed: ${error.message}`);
    }
  }

  private async createItem(boardId: string, data: any): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: `mutation { create_item (board_id: ${boardId}, item_name: "${data.name}") { id name } }` }, {
        headers: { Authorization: this.config.apiKey },
      });
      return { success: true, item: response.data.data.create_item };
    } catch (error: any) {
      throw new Error(`Monday createItem failed: ${error.message}`);
    }
  }

  private async updateItem(itemId: string, data: any): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: `mutation { change_column_value (item_id: ${itemId}, column_id: "${data.columnId}", value: "${data.value}") { id } }` }, {
        headers: { Authorization: this.config.apiKey },
      });
      return { success: true, item: response.data.data.change_column_value };
    } catch (error: any) {
      throw new Error(`Monday updateItem failed: ${error.message}`);
    }
  }

  private async deleteItem(itemId: string): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: `mutation { delete_item (item_id: ${itemId}) { id } }` }, {
        headers: { Authorization: this.config.apiKey },
      });
      return { success: true, item: response.data.data.delete_item };
    } catch (error: any) {
      throw new Error(`Monday deleteItem failed: ${error.message}`);
    }
  }

  private async getColumns(boardId: string): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: `{ boards (ids: [${boardId}]) { columns { id title type } } }` }, {
        headers: { Authorization: this.config.apiKey },
      });
      return { success: true, columns: response.data.data.boards[0].columns };
    } catch (error: any) {
      throw new Error(`Monday getColumns failed: ${error.message}`);
    }
  }
}
