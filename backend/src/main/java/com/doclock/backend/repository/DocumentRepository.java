package com.doclock.backend.repository;
import com.doclock.backend.entity.Document; import org.springframework.data.jpa.repository.JpaRepository; import java.util.List;
public interface DocumentRepository extends JpaRepository<Document,Long>{ List<Document> findByOriginalFilenameContainingIgnoreCaseOrderByUploadedAtDesc(String q); List<Document> findAllByOrderByUploadedAtDesc(); }
