declare module 'node-trello' {
  class Trello {
    constructor(key: string, token: string);
    get(path: string, callback: (err: any, data: any) => void): void;
    post(path: string, data: any, callback: (err: any, data: any) => void): void;
    put(path: string, data: any, callback: (err: any, data: any) => void): void;
    del(path: string, callback: (err: any, data: any) => void): void;
  }

  export default Trello;
}
