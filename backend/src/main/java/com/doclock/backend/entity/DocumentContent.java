package com.doclock.backend.entity;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "document_contents")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DocumentContent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "document_id", nullable = false, unique = true)
    private Document document;

    @Column(columnDefinition = "TEXT", nullable = false)
    private String extractedText;

    private Integer wordCount;
}
