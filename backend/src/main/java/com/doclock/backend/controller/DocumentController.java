package com.doclock.backend.controller;

import com.doclock.backend.entity.Document;
import com.doclock.backend.service.DocumentService;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Files;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) { this.service = service; }

    @GetMapping
    public List<Document> list(@RequestParam(required = false) String q) {
        return service.list(q);
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Document upload(@RequestParam("file") MultipartFile file) throws Exception {
        return service.upload(file);
    }

    @GetMapping("/{id}")
    public Document get(@PathVariable Long id) { return service.get(id); }

    @GetMapping("/{id}/content")
    public Map<String, String> content(@PathVariable Long id) {
        return Map.of("content", service.text(id));
    }

    /** Streams a browser-friendly preview for PDF, image and text files. */
    @GetMapping("/{id}/view")
    public ResponseEntity<byte[]> view(@PathVariable Long id) throws Exception {
        Document document = service.get(id);
        byte[] fileBytes = Files.readAllBytes(service.path(id));
        MediaType type;
        try {
            type = MediaType.parseMediaType(document.getContentType());
        } catch (Exception ignored) {
            type = MediaType.APPLICATION_OCTET_STREAM;
        }
        return ResponseEntity.ok()
                .contentType(type)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.inline().filename(document.getOriginalFilename()).build().toString())
                .body(fileBytes);
    }

    @GetMapping("/{id}/download")
    public ResponseEntity<byte[]> download(@PathVariable Long id) throws Exception {
        Document document = service.get(id);
        byte[] fileBytes = Files.readAllBytes(service.path(id));
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment().filename(document.getOriginalFilename()).build().toString())
                .body(fileBytes);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) throws Exception {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
