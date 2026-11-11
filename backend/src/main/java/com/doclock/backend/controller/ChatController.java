package com.doclock.backend.controller;

import com.doclock.backend.dto.ChatRequest;
import com.doclock.backend.entity.ChatMessage;
import com.doclock.backend.service.AiService;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/chat")
public class ChatController {
    private final AiService aiService;

    public ChatController(AiService aiService) {
        this.aiService = aiService;
    }

    @PostMapping
    public Map<String, Object> chat(@RequestBody ChatRequest request) {
        return aiService.chat(request);
    }

    @GetMapping("/conversations")
    public List<Map<String, Object>> conversations() {
        return aiService.conversations().stream().map(conversation -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", conversation.getId());
            item.put("title", conversation.getTitle());
            item.put("createdAt", conversation.getCreatedAt());
            item.put("updatedAt", conversation.getUpdatedAt());
            return item;
        }).toList();
    }

    // Return a small response object instead of serializing the JPA relationship.
    // This prevents recursive conversation -> messages -> conversation JSON.
    @GetMapping("/conversations/{id}/messages")
    public List<Map<String, Object>> messages(@PathVariable Long id) {
        return aiService.history(id).stream().map(this::messageResponse).toList();
    }

    private Map<String, Object> messageResponse(ChatMessage message) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("id", message.getId());
        item.put("role", message.getRole());
        item.put("content", message.getContent());
        item.put("citations", message.getCitationsJson());
        item.put("timestamp", message.getTimestamp());
        return item;
    }
}
