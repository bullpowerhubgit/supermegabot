import { TrelloConfig, TrelloAction } from './types.js';
import Trello from 'node-trello';

export class TrelloController {
  private config: TrelloConfig;
  private client: Trello;

  constructor(config: TrelloConfig) {
    this.config = config;
    this.client = new Trello(config.apiKey, config.token);
  }

  async execute(action: TrelloAction): Promise<any> {
    switch (action.action) {
      case 'getBoards':
        return this.getBoards();
      case 'getBoard':
        return this.getBoard(action.boardId!);
      case 'getLists':
        return this.getLists(action.boardId!);
      case 'getList':
        return this.getList(action.listId!);
      case 'getCards':
        return this.getCards(action.listId!);
      case 'getCard':
        return this.getCard(action.cardId!);
      case 'createCard':
        return this.createCard(action.listId!, action.data);
      case 'updateCard':
        return this.updateCard(action.cardId!, action.data);
      case 'deleteCard':
        return this.deleteCard(action.cardId!);
      case 'createList':
        return this.createList(action.boardId!, action.data);
      default:
        throw new Error(`Unknown Trello action: ${action.action}`);
    }
  }

  private async getBoards(): Promise<any> {
    try {
      const boards = await new Promise((resolve, reject) => {
        this.client.get('/1/members/me/boards', (err: any, data: any) => {
          if (err) reject(err);
          else resolve(data);
        });
      });
      return { success: true, boards };
    } catch (error: any) {
      throw new Error(`Trello getBoards failed: ${error.message}`);
    }
  }

  private async getBoard(boardId: string): Promise<any> {
    try {
      const board = await new Promise((resolve, reject) => {
        this.client.get(`/1/boards/${boardId}`, (err: any, data: any) => {
          if (err) reject(err);
          else resolve(data);
        });
      });
      return { success: true, board };
    } catch (error: any) {
      throw new Error(`Trello getBoard failed: ${error.message}`);
    }
  }

  private async getLists(boardId: string): Promise<any> {
    try {
      const lists = await new Promise((resolve, reject) => {
        this.client.get(`/1/boards/${boardId}/lists`, (err: any, data: any) => {
          if (err) reject(err);
          else resolve(data);
        });
      });
      return { success: true, lists };
    } catch (error: any) {
      throw new Error(`Trello getLists failed: ${error.message}`);
    }
  }

  private async getList(listId: string): Promise<any> {
    try {
      const list = await new Promise((resolve, reject) => {
        this.client.get(`/1/lists/${listId}`, (err: any, data: any) => {
          if (err) reject(err);
          else resolve(data);
        });
      });
      return { success: true, list };
    } catch (error: any) {
      throw new Error(`Trello getList failed: ${error.message}`);
    }
  }

  private async getCards(listId: string): Promise<any> {
    try {
      const cards = await new Promise((resolve, reject) => {
        this.client.get(`/1/lists/${listId}/cards`, (err: any, data: any) => {
          if (err) reject(err);
          else resolve(data);
        });
      });
      return { success: true, cards };
    } catch (error: any) {
      throw new Error(`Trello getCards failed: ${error.message}`);
    }
  }

  private async getCard(cardId: string): Promise<any> {
    try {
      const card = await new Promise((resolve, reject) => {
        this.client.get(`/1/cards/${cardId}`, (err: any, data: any) => {
          if (err) reject(err);
          else resolve(data);
        });
      });
      return { success: true, card };
    } catch (error: any) {
      throw new Error(`Trello getCard failed: ${error.message}`);
    }
  }

  private async createCard(listId: string, data: any): Promise<any> {
    try {
      const card = await new Promise((resolve, reject) => {
        this.client.post(`/1/cards`, { idList: listId, ...data }, (err: any, data: any) => {
          if (err) reject(err);
          else resolve(data);
        });
      });
      return { success: true, card };
    } catch (error: any) {
      throw new Error(`Trello createCard failed: ${error.message}`);
    }
  }

  private async updateCard(cardId: string, data: any): Promise<any> {
    try {
      const card = await new Promise((resolve, reject) => {
        this.client.put(`/1/cards/${cardId}`, data, (err: any, data: any) => {
          if (err) reject(err);
          else resolve(data);
        });
      });
      return { success: true, card };
    } catch (error: any) {
      throw new Error(`Trello updateCard failed: ${error.message}`);
    }
  }

  private async deleteCard(cardId: string): Promise<any> {
    try {
      await new Promise((resolve, reject) => {
        this.client.del(`/1/cards/${cardId}`, (err: any, data: any) => {
          if (err) reject(err);
          else resolve(data);
        });
      });
      return { success: true, message: 'Card deleted' };
    } catch (error: any) {
      throw new Error(`Trello deleteCard failed: ${error.message}`);
    }
  }

  private async createList(boardId: string, data: any): Promise<any> {
    try {
      const list = await new Promise((resolve, reject) => {
        this.client.post(`/1/lists`, { idBoard: boardId, ...data }, (err: any, data: any) => {
          if (err) reject(err);
          else resolve(data);
        });
      });
      return { success: true, list };
    } catch (error: any) {
      throw new Error(`Trello createList failed: ${error.message}`);
    }
  }
}
