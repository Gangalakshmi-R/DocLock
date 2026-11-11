package com.doclock.backend.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Creates text embeddings through the local Ollama service. */
@Service
public class EmbeddingService {
    private final RestClient http;

    @Value("${doclock.ai.ollama.base-url}")
    private String baseUrl;

    @Value("${doclock.ai.ollama.embed-model}")
    private String model;

    public EmbeddingService(RestClient http) {
        this.http = http;
    }

    public List<Double> embed(String text) {
        if (text == null || text.isBlank()) {
            return List.of();
        }

        // Current Ollama endpoint. It returns an "embeddings" array.
        try {
            Map<?, ?> response = http.post()
                    .uri(baseUrl + "/api/embed")
                    .body(Map.of("model", model, "input", text))
                    .retrieve()
                    .body(Map.class);

            if (response != null && response.get("embeddings") instanceof List<?> rows
                    && !rows.isEmpty() && rows.get(0) instanceof List<?> values) {
                return toNumbers(values);
            }
        } catch (Exception ignored) {
            // Try the older Ollama endpoint for compatibility with older installations.
        }

        try {
            Map<?, ?> response = http.post()
                    .uri(baseUrl + "/api/embeddings")
                    .body(Map.of("model", model, "prompt", text))
                    .retrieve()
                    .body(Map.class);

            if (response != null && response.get("embedding") instanceof List<?> values) {
                return toNumbers(values);
            }
        } catch (Exception ignored) {
            // Keyword retrieval remains available when Ollama is offline.
        }

        return List.of();
    }

    private List<Double> toNumbers(List<?> values) {
        List<Double> vector = new ArrayList<>();
        for (Object value : values) {
            if (!(value instanceof Number number)) {
                return List.of();
            }
            vector.add(number.doubleValue());
        }
        return vector;
    }

    public double cosine(List<Double> first, List<Double> second) {
        if (first == null || second == null || first.isEmpty() || first.size() != second.size()) {
            return 0;
        }

        double dot = 0;
        double firstLength = 0;
        double secondLength = 0;

        for (int index = 0; index < first.size(); index++) {
            dot += first.get(index) * second.get(index);
            firstLength += first.get(index) * first.get(index);
            secondLength += second.get(index) * second.get(index);
        }

        if (firstLength == 0 || secondLength == 0) {
            return 0;
        }

        return dot / (Math.sqrt(firstLength) * Math.sqrt(secondLength));
    }
}
