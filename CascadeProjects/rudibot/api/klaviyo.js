/**
 * Klaviyo API Integration für RUDIBOT
 * Marketing Automation, E-Mail/SMS, Profile Tracking
 */

class KlaviyoService {
  constructor() {
    this.apiKey = process.env.KLAVIYO_API_KEY;
    this.baseURL = 'https://a.klaviyo.com/api';
  }

  async klaviyoFetch(endpoint, options = {}) {
    const url = `${this.baseURL}/${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Authorization': `Klaviyo-API-Key ${this.apiKey}`,
        'revision': '2023-02-22',
        'Content-Type': 'application/json',
        ...options.headers
      }
    });
    
    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Klaviyo API ${response.status}: ${error}`);
    }
    
    return response.json();
  }

  // Profile verwalten
  async createOrUpdateProfile(email, properties = {}) {
    try {
      const profile = await this.klaviyoFetch('profiles/', {
        method: 'POST',
        body: JSON.stringify({
          data: {
            type: 'profile',
            attributes: {
              email: email,
              properties: properties
            }
          }
        })
      });
      return { success: true, profile };
    } catch (error) {
      console.error('Klaviyo Profile Error:', error);
      return { success: false, error: error.message };
    }
  }

  // Events tracken
  async trackEvent(profileId, eventName, properties = {}) {
    try {
      const event = await this.klaviyoFetch('events/', {
        method: 'POST',
        body: JSON.stringify({
          data: {
            type: 'event',
            attributes: {
              profile: {
                data: {
                  type: 'profile',
                  id: profileId
                }
              },
              metric: {
                data: {
                  type: 'metric',
                  attributes: {
                    name: eventName
                  }
                }
              },
              properties: properties,
              time: new Date().toISOString()
            }
          }
        })
      });
      return { success: true, event };
    } catch (error) {
      console.error('Klaviyo Event Error:', error);
      return { success: false, error: error.message };
    }
  }

  // Shopify-Events an Klaviyo senden
  async trackShopifyOrder(orderData) {
    try {
      // Profile erstellen/aktualisieren
      const profileResult = await this.createOrUpdateProfile(orderData.email, {
        first_name: orderData.first_name,
        last_name: orderData.last_name,
        phone: orderData.phone,
        location: orderData.location
      });

      if (!profileResult.success) {
        return profileResult;
      }

      // Bestell-Event tracken
      const eventResult = await this.trackEvent(
        profileResult.profile.data.id,
        'Placed Order',
        {
          order_id: orderData.id,
          total: orderData.total,
          currency: orderData.currency,
          items: orderData.items
        }
      );

      return eventResult;
    } catch (error) {
      console.error('Shopify Order Tracking Error:', error);
      return { success: false, error: error.message };
    }
  }

  // Kampagne auslösen
  async triggerCampaign(campaignId, profileIds = []) {
    try {
      const campaign = await this.klaviyoFetch(`campaigns/${campaignId}/send`, {
        method: 'POST',
        body: JSON.stringify({
          data: {
            type: 'campaign',
            id: campaignId,
            attributes: {
              profile_ids: profileIds
            }
          }
        })
      });
      return { success: true, campaign };
    } catch (error) {
      console.error('Klaviyo Campaign Error:', error);
      return { success: false, error: error.message };
    }
  }

  // Listen abrufen
  async getLists() {
    try {
      const response = await this.klaviyoFetch('lists/');
      return { success: true, data: response.data };
    } catch (error) {
      console.error('Klaviyo Lists Error:', error);
      return { success: false, error: error.message };
    }
  }

  // Profile zu Liste hinzufügen
  async addProfileToList(listId, profileIds) {
    try {
      const result = await this.klaviyoFetch(`lists/${listId}/relationships/profiles/`, {
        method: 'POST',
        body: JSON.stringify({
          data: profileIds.map(id => ({
            type: 'profile',
            id: id
          }))
        })
      });
      return { success: true, result };
    } catch (error) {
      console.error('Klaviyo Add to List Error:', error);
      return { success: false, error: error.message };
    }
  }
}

module.exports = KlaviyoService;
