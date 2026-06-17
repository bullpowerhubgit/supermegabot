declare module 'heroku-client' {
  interface HerokuOptions {
    token: string;
  }

  interface HerokuResponse<T = any> {
    body: T;
  }

  class Heroku {
    constructor(options: HerokuOptions);
    get(path: string): Promise<any>;
    post(path: string, options?: any): Promise<any>;
    put(path: string, options?: any): Promise<any>;
    delete(path: string): Promise<any>;
  }

  export default Heroku;
}
