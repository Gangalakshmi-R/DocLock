package com.doclock.backend.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Small REST client for ChromaDB. PostgreSQL remains the source of truth for document records. */
@Service
public class ChromaService {
    private static final String TENANT = "default_tenant";
    private static final String DATABASE = "default_database";

    private final RestClient http;

    @Value("${doclock.ai.chroma.base-url}")
    private String chromaUrl;

    @Value("${doclock.ai.chroma.collection-name}")
    private String collectionName;

    private volatile String collectionId;

    public ChromaService(RestClient http) {
        this.http = http;
    }

    /** Store one document passage in Chroma. Returns false when Chroma is temporarily unavailable. */
    public boolean upsert(String id, List<Double> vector, String text, Long documentId,
                          String filename, int chunkIndex) {
        if (vector == null || vector.isEmpty()) return false;
        try {
            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("documentId", documentId);
            metadata.put("filename", filename);
            metadata.put("chunkIndex", chunkIndex);

            Map<String, Object> body = new LinkedHashMap<>();
            body.put("ids", List.of(id));
            body.put("embeddings", List.of(vector));
            body.put("documents", List.of(text));
            body.put("metadatas", List.of(metadata));

            http.post().uri(collectionUrl() + "/upsert").body(body).retrieve().toBodilessEntity();
            return true;
        } catch (Exception exception) {
            // The application also stores vectors in PostgreSQL as a safe fallback.
            return false;
        }
    }

    /** Returns Chroma passage IDs ordered by semantic similarity. */
    public List<String> query(List<Double> vector, Long documentId, int limit) {
        if (vector == null || vector.isEmpty()) return List.of();
        try {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("query_embeddings", List.of(vector));
            body.put("n_results", limit);
            if (documentId != null) {
                body.put("where", Map.of("documentId", Map.of("$eq", documentId)));
            }

            Map<?, ?> response = http.post().uri(collectionUrl() + "/query")
                    .body(body).retrieve().body(Map.class);
            if (response == null || !(response.get("ids") instanceof List<?> idRows)
                    || idRows.isEmpty() || !(idRows.get(0) instanceof List<?> ids)) {
                return List.of();
            }

            List<String> result = new ArrayList<>();
            for (Object id : ids) {
                if (id != null) result.add(id.toString());
            }
            return result;
        } catch (Exception exception) {
            return List.of();
        }
    }

    /** Remove vector records after the matching PostgreSQL document is deleted. */
    public void delete(List<String> ids) {
        if (ids == null || ids.isEmpty()) return;
        try {
            http.post().uri(collectionUrl() + "/delete")
                    .body(Map.of("ids", ids)).retrieve().toBodilessEntity();
        } catch (Exception ignored) {
            // PostgreSQL deletion must still complete; stale vectors can be overwritten on re-upload.
        }
    }

    private String collectionUrl() {
        return chromaUrl + "/api/v2/tenants/" + TENANT + "/databases/" + DATABASE
                + "/collections/" + ensureCollectionId();
    }

    private String ensureCollectionId() {
        if (collectionId != null) return collectionId;
        synchronized (this) {
            if (collectionId != null) return collectionId;
            String base = chromaUrl + "/api/v2/tenants/" + TENANT + "/databases/" + DATABASE + "/collections";
            try {
                Map<?, ?> existing = http.get().uri(base + "/" + collectionName)
                        .retrieve().body(Map.class);
                if (existing != null && existing.get("id") != null) {
                    collectionId = existing.get("id").toString();
                    return collectionId;
                }
            } catch (Exception ignored) {
                // The collection may not exist yet; create it below.
            }

            Map<?, ?> created = http.post().uri(base)
                    .body(Map.of("name", collectionName, "metadata", Map.of("hnsw:space", "cosine")))
                    .retrieve().body(Map.class);
            if (created == null || created.get("id") == null) {
                throw new IllegalStateException("ChromaDB did not return a collection ID.");
            }
            collectionId = created.get("id").toString();
            return collectionId;
        }
    }
}
