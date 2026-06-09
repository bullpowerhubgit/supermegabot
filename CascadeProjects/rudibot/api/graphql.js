/**
 * GraphQL API für RUDIBOT
 * Integration mit Klaviyo und GraphQL WG Dokumenten
 */

const { ApolloServer, gql } = require('@apollo/server');
const { startServerAndCreateLambdaHandler } = require('@apollo/server-integration-fastify');
const KlaviyoService = require('./klaviyo');

const klaviyo = new KlaviyoService();

// GraphQL Schema Definition
const typeDefs = gql`
  type Profile {
    id: ID!
    email: String!
    properties: JSON
    createdAt: String
  }

  type Event {
    id: ID!
    name: String!
    profile: Profile!
    properties: JSON
    timestamp: String
  }

  type Campaign {
    id: ID!
    name: String!
    status: String
    profiles: [Profile!]!
  }

  type GraphQLWGMeeting {
    id: ID!
    date: String!
    title: String!
    agenda: String!
    attendees: [String!]!
    decisions: [String!]!
  }

  type Query {
    # Klaviyo Queries
    profiles(email: String): [Profile!]!
    events(profileId: ID): [Event!]!
    campaigns: [Campaign!]!
    
    # GraphQL WG Queries
    graphqlMeetings(year: Int, month: Int): [GraphQLWGMeeting!]!
    graphqlMeeting(id: ID!): GraphQLWGMeeting
    
    # Combined Queries
    profileWithEvents(email: String!): Profile
  }

  type Mutation {
    # Klaviyo Mutations
    createProfile(email: String!, properties: JSON): Profile!
    trackEvent(profileId: ID!, eventName: String!, properties: JSON): Event!
    triggerCampaign(campaignId: ID!, profileIds: [ID!]!): Campaign!
    
    # GraphQL WG Mutations
    addGraphQLMeeting(meeting: GraphQLWGMeetingInput!): GraphQLWGMeeting!
    
    # Combined Mutations
    createProfileAndTrackEvent(email: String!, properties: JSON!, eventName: String!, eventProperties: JSON): Profile!
  }

  input GraphQLWGMeetingInput {
    date: String!
    title: String!
    agenda: String!
    attendees: [String!]!
    decisions: [String!]!
  }

  scalar JSON
`;

// Resolvers
const resolvers = {
  Query: {
    // Klaviyo Queries
    profiles: async (_, { email }) => {
      // Implement profile lookup
      return [];
    },
    
    events: async (_, { profileId }) => {
      // Implement event lookup
      return [];
    },
    
    campaigns: async () => {
      const result = await klaviyo.getLists();
      return result.success ? result.lists : [];
    },
    
    // GraphQL WG Queries
    graphqlMeetings: async (_, { year, month }) => {
      // Parse GraphQL WG documents
      return await parseGraphQLWgMeetings(year, month);
    },
    
    graphqlMeeting: async (_, { id }) => {
      // Get specific meeting
      return null;
    },
    
    profileWithEvents: async (_, { email }) => {
      // Combined profile + events
      return null;
    }
  },

  Mutation: {
    // Klaviyo Mutations
    createProfile: async (_, { email, properties }) => {
      const result = await klaviyo.createOrUpdateProfile(email, properties);
      if (!result.success) {
        throw new Error(result.error);
      }
      return result.profile.data;
    },
    
    trackEvent: async (_, { profileId, eventName, properties }) => {
      const result = await klaviyo.trackEvent(profileId, eventName, properties);
      if (!result.success) {
        throw new Error(result.error);
      }
      return result.event.data;
    },
    
    triggerCampaign: async (_, { campaignId, profileIds }) => {
      const result = await klaviyo.triggerCampaign(campaignId, profileIds);
      if (!result.success) {
        throw new Error(result.error);
      }
      return result.campaign.data;
    },
    
    // GraphQL WG Mutations
    addGraphQLMeeting: async (_, { meeting }) => {
      // Store meeting data
      return meeting;
    },
    
    // Combined Mutations
    createProfileAndTrackEvent: async (_, { email, properties, eventName, eventProperties }) => {
      // Create profile first
      const profileResult = await klaviyo.createOrUpdateProfile(email, properties);
      if (!profileResult.success) {
        throw new Error(profileResult.error);
      }
      
      // Then track event
      const eventResult = await klaviyo.trackEvent(
        profileResult.profile.data.id,
        eventName,
        eventProperties
      );
      
      if (!eventResult.success) {
        throw new Error(eventResult.error);
      }
      
      return profileResult.profile.data;
    }
  }
};

// GraphQL WG Meeting Parser
async function parseGraphQLWgMeetings(year, month) {
  // This would parse the GraphQL WG documents
  // For now, return mock data
  return [
    {
      id: 'wg-2026-06',
      date: '2026-06-09',
      title: 'GraphQL WG June 2026',
      agenda: 'Agenda items...',
      attendees: ['@member1', '@member2'],
      decisions: ['Decision 1', 'Decision 2']
    }
  ];
}

// Apollo Server Setup
const server = new ApolloServer({
  typeDefs,
  resolvers,
  formatError: (error) => {
    console.error('GraphQL Error:', error);
    return {
      message: error.message,
      code: error.extensions?.code || 'INTERNAL_SERVER_ERROR'
    };
  }
});

module.exports = server;
