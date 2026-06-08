declare module 'mailgun-js' {
  interface MailgunOptions {
    apiKey: string;
    domain: string;
  }

  interface Mailgun {
    messages(): any;
    get(path: string, callback: (err: any, body: any) => void): void;
    delete(path: string, callback: (err: any, body: any) => void): void;
  }

  namespace mailgun {
    function mailgun(options: MailgunOptions): Mailgun;
  }

  function mailgun(options: MailgunOptions): Mailgun;
  export = mailgun;
}
