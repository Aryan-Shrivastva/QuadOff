# Judge walkthrough

**Question.** “Has low dissolved oxygen or high turbidity been reported near
River Zone 3 before?”

1. Start the edge service and UI. Point out the Qdrant Edge badge and local
   vector count.
2. Search the question. Read the local briefing, then open the matching
   observations. Call out the 4.2/4.8 mg/L oxygen readings and 15.0/18.4 NTU
   turbidity readings.
3. Toggle **Offline**. Search the same question again. The origin remains
   Qdrant Edge, the response includes an offline flag, and no network call is
   needed.
4. Capture a note with **Needs verification**. It is immediately indexed but
   stays out of the sync queue.
5. Capture or approve a second note with **Ready to sync**. The SQLite outbox
   shows one explicit update.
6. Toggle **Online**. Reconnection automatically flushes the approved outbox to
   Qdrant Server; show the acknowledgement and the queue returning to zero.
7. Open the seeded conflict through `/api/conflicts`; resolve local, remote, or
   merged content. Explain that no update silently overwrites another one.

The pack is a small, reproducible fixture shaped from USGS Water Data API and
EPA Water Quality Portal fields. Its manifest labels joined measurements and
weather context as demo-created rather than presenting them as live official
readings.
