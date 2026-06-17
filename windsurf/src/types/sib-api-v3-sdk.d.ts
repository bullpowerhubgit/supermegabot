declare module 'sib-api-v3-sdk' {
  class ApiClient {
    static instance: ApiClient;
    authentications: any;
  }

  class ContactsApi {
    getContacts(limit?: number): Promise<any>;
    getContactInfo(id: string): Promise<any>;
    createContact(contact: any): Promise<any>;
    updateContact(id: string, contact: any): Promise<any>;
    deleteContact(id: string): Promise<any>;
  }

  class TransactionalEmailsApi {
    sendTransacEmail(email: any): Promise<any>;
  }

  class EmailCampaignsApi {
    getEmailCampaigns(limit?: number): Promise<any>;
  }

  class TransactionalSMSApi {
    sendTransacSms(sms: any): Promise<any>;
  }

  export { ApiClient, ContactsApi, TransactionalEmailsApi, EmailCampaignsApi, TransactionalSMSApi };
}
