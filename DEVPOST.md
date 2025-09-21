# TransactAI: Natural Language E-commerce with AI Agents

## Inspiration
The future of e-commerce lies in natural conversation. We wanted to create a system where users could order products as naturally as talking to a friend, while demonstrating the power of Google Cloud's microservices architecture and AI capabilities.

## What it does
TransactAI is a natural language e-commerce interface that:
- Understands natural language product requests
- Integrates with Google's Online Boutique demo store
- Uses AI agents to handle orders and payments
- Provides real-time order tracking and payment processing
- Demonstrates microservices communication using A2A and MCP protocols

## How we built it
1. **Architecture**:
   - Orchestrator AI Agent (Gemini + Streamlit)
   - Order Agent (MCP Protocol)
   - Payment AI Agent (A2A Protocol)
   - Payment Server
   - Online Boutique integration

2. **Technologies**:
   - Google Cloud GKE for Online Boutique deployment
   - Google Gemini Pro for natural language understanding
   - FastAPI for microservices
   - Streamlit for UI
   - Python for backend logic

3. **Protocols**:
   - Agent-to-Agent (A2A) for payment processing
   - Model Context Protocol (MCP) for service discovery

## Challenges we ran into
1. **Online Boutique Integration**:
   - Understanding the API structure
   - Handling HTML responses instead of JSON
   - Managing session cookies for cart/checkout

2. **AI Model Integration**:
   - Migrating from local LLaMA2 to Gemini
   - Handling safety settings and content filtering
   - Ensuring consistent JSON outputs

3. **Microservices Communication**:
   - Implementing A2A and MCP protocols
   - Managing state across services
   - Handling error cases gracefully

## Accomplishments that we're proud of
1. Seamless natural language ordering experience
2. Successful integration with Online Boutique
3. Implementation of two different agent communication protocols
4. Clean and intuitive user interface
5. Robust error handling and user feedback

## What we learned
1. Google Cloud GKE deployment strategies
2. Microservices communication patterns
3. AI model prompt engineering
4. Session management in distributed systems
5. Error handling in AI applications

## What's next for TransactAI
1. **Enhanced AI Capabilities**:
   - Product recommendations
   - Price negotiation
   - Multi-language support

2. **Technical Improvements**:
   - Kubernetes auto-scaling
   - Caching and performance optimization
   - More payment methods

3. **User Experience**:
   - Voice interface
   - Mobile app
   - Order history and analytics

## Built With
- google-cloud
- kubernetes
- python
- fastapi
- streamlit
- gemini-pro
- online-boutique

## Try it out
- [GitHub Repository](your-repo-url)
- [Demo Video](your-video-url)
- [Live Demo](your-demo-url) (if available)
